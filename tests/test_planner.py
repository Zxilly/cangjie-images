from __future__ import annotations

import json

import httpx
import pytest

import cangjie_images.planner as planner
from cangjie_images.planner import (
    _compute_stable_heads,
    build_plan,
    build_tags,
    merge_release_manifests,
    scan_committed_versions,
    write_digest_metadata,
)


def _write_dockerfile(
    versions_root,
    channel: str,
    version: str,
    base: str,
    arches: tuple[str, ...] = ("amd64", "arm64"),
) -> None:
    for arch in arches:
        target = versions_root / channel / version / base / arch / "Dockerfile"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            f"FROM scratch AS sdk\nADD --checksum=sha256:{'0' * 64} url /sdk.tar.gz\n",
            encoding="utf-8",
        )


def _seed_versions(versions_root) -> None:
    _write_dockerfile(versions_root, "lts", "1.0.4", "bookworm")
    _write_dockerfile(versions_root, "lts", "1.0.4", "trixie")
    _write_dockerfile(versions_root, "lts", "1.0.5", "bookworm")
    _write_dockerfile(versions_root, "lts", "1.0.5", "trixie")
    _write_dockerfile(versions_root, "sts", "0.53.18", "bookworm")


def sample_nightly_release(
    version: str = "1.1.0-alpha.20260306010001",
    *,
    include_arm64: bool = True,
) -> dict:
    assets = [
        {
            "name": f"cangjie-sdk-linux-x64-{version}.tar.gz",
            "browser_download_url": f"https://example.com/nightly/{version}/amd64.tar.gz",
        }
    ]
    if include_arm64:
        assets.append(
            {
                "name": f"cangjie-sdk-linux-aarch64-{version}.tar.gz",
                "browser_download_url": f"https://example.com/nightly/{version}/arm64.tar.gz",
            }
        )
    return {"tag_name": version, "assets": assets}


def test_scan_committed_versions(tmp_path) -> None:
    _seed_versions(tmp_path)
    found = scan_committed_versions(tmp_path)
    combos = {(e.channel, e.version, e.base, e.arch) for e in found}
    assert ("lts", "1.0.5", "bookworm", "amd64") in combos
    assert ("lts", "1.0.5", "bookworm", "arm64") in combos
    assert ("sts", "0.53.18", "bookworm", "amd64") in combos


def test_scan_committed_versions_ignores_unknown_dirs(tmp_path) -> None:
    _write_dockerfile(tmp_path, "lts", "1.0.5", "bookworm")
    # Unsupported channel name.
    _write_dockerfile(tmp_path, "xyz", "1.0.5", "bookworm")
    # Unsupported base name.
    _write_dockerfile(tmp_path, "lts", "1.0.5", "alpine")
    # Unsupported arch name.
    bad_arch = tmp_path / "lts" / "1.0.5" / "bookworm" / "riscv64" / "Dockerfile"
    bad_arch.parent.mkdir(parents=True, exist_ok=True)
    bad_arch.write_text("FROM scratch\n", encoding="utf-8")

    found = scan_committed_versions(tmp_path)
    bases_seen = {(e.channel, e.base, e.arch) for e in found}
    assert bases_seen <= {
        ("lts", "bookworm", "amd64"),
        ("lts", "bookworm", "arm64"),
    }


def test_scan_committed_skips_base_dirs_without_dockerfile(tmp_path) -> None:
    stray = tmp_path / "lts" / "1.0.5" / "bookworm" / "amd64"
    stray.mkdir(parents=True)
    (stray / "README.md").write_text("no dockerfile here", encoding="utf-8")
    assert scan_committed_versions(tmp_path) == []


def test_compute_stable_heads_picks_latest() -> None:
    from pathlib import Path

    committed = [
        planner.CommittedDockerfile("lts", "1.0.4", "bookworm", "amd64", Path("/x")),
        planner.CommittedDockerfile("lts", "1.0.5", "bookworm", "amd64", Path("/x")),
        planner.CommittedDockerfile("sts", "0.53.18", "bookworm", "amd64", Path("/x")),
    ]
    latest_lts, latest_sts, minor_aliases = _compute_stable_heads(committed)
    assert latest_lts == "1.0.5"
    assert latest_sts == "0.53.18"
    assert minor_aliases["1.0.5"] == ("1.0",)
    assert minor_aliases["0.53.18"] == ("0.53",)


def test_build_tags_for_default_lts_base() -> None:
    tags = build_tags(
        channel="lts",
        version="1.0.5",
        base_name="bookworm",
        default_base=True,
        latest_lts="1.0.5",
        latest_sts="0.53.18",
        minor_aliases={"1.0.5": ("1.0",)},
    )
    assert tags == (
        "1.0.5",
        "1.0.5-bookworm",
        "1.0",
        "1.0-bookworm",
        "lts",
        "lts-bookworm",
        "latest",
        "latest-bookworm",
    )


def test_build_plan_skips_release_when_all_tags_exist(tmp_path) -> None:
    _seed_versions(tmp_path)
    existing_tags = {
        "1.0.5",
        "1.0.5-bookworm",
        "1.0",
        "1.0-bookworm",
        "lts",
        "lts-bookworm",
        "latest",
        "latest-bookworm",
    }
    plan = build_plan(
        image_name="zxilly/cangjie",
        include_nightly=False,
        versions_root=tmp_path,
        existing_tags=existing_tags,
    )
    release_ids = {release.release_id for release in plan.publish_matrix}
    assert "lts-1-0-5-bookworm" not in release_ids
    assert "lts-1-0-4-bookworm" in release_ids


def test_build_plan_keeps_release_when_existing_missing_arch(tmp_path) -> None:
    _seed_versions(tmp_path)
    existing_tags = {
        "1.0.5": {"amd64", "arm64"},
        "1.0.5-bookworm": {"amd64"},
        "1.0": {"amd64", "arm64"},
        "1.0-bookworm": {"amd64", "arm64"},
        "lts": {"amd64", "arm64"},
        "lts-bookworm": {"amd64", "arm64"},
        "latest": {"amd64", "arm64"},
        "latest-bookworm": {"amd64", "arm64"},
    }
    plan = build_plan(
        image_name="zxilly/cangjie",
        include_nightly=False,
        versions_root=tmp_path,
        existing_tags=existing_tags,
    )
    release_ids = {release.release_id for release in plan.publish_matrix}
    assert "lts-1-0-5-bookworm" in release_ids


def test_build_plan_keeps_release_when_moving_aliases_are_stale(tmp_path) -> None:
    _seed_versions(tmp_path)
    current = {"amd64": "sha256:new-amd64", "arm64": "sha256:new-arm64"}
    stale = {"amd64": "sha256:old-amd64", "arm64": "sha256:old-arm64"}
    existing_tags = {
        "1.0.5": current,
        "1.0.5-bookworm": current,
        "1.0": current,
        "1.0-bookworm": current,
        "lts": stale,
        "lts-bookworm": stale,
        "latest": stale,
        "latest-bookworm": stale,
    }
    plan = build_plan(
        image_name="zxilly/cangjie",
        include_nightly=False,
        versions_root=tmp_path,
        existing_tags=existing_tags,
    )
    release_ids = {release.release_id for release in plan.publish_matrix}
    assert "lts-1-0-5-bookworm" in release_ids


def test_build_plan_points_at_committed_context_dir(tmp_path) -> None:
    _write_dockerfile(tmp_path, "lts", "1.0.5", "bookworm")
    plan = build_plan(
        image_name="zxilly/cangjie",
        include_nightly=False,
        versions_root=tmp_path,
        existing_tags=set(),
    )
    assert plan.build_matrix
    for build in plan.build_matrix:
        assert build.context_dir.endswith(build.arch)


def test_build_plan_empty_versions_root_has_no_work(tmp_path) -> None:
    plan = build_plan(
        image_name="zxilly/cangjie",
        include_nightly=False,
        versions_root=tmp_path,
        existing_tags=set(),
    )
    assert plan.build_matrix == ()
    assert plan.publish_matrix == ()


def test_build_plan_adds_nightly_tags(tmp_path, monkeypatch) -> None:
    _write_dockerfile(tmp_path, "lts", "1.0.5", "bookworm")
    nightly_ctx = tmp_path / "nightly-ctx"

    recorded: dict[str, object] = {}

    def fake_render_nightly(release, platforms, output_root, bases=None):
        recorded["output_root"] = output_root
        recorded["bases"] = bases
        selected = bases if bases is not None else tuple()
        contexts = {}
        for base in selected:
            for arch in ("amd64", "arm64"):
                ctx = output_root / f"nightly-{release.tag_name}-{base.name}-{arch}"
                ctx.mkdir(parents=True, exist_ok=True)
                (ctx / "Dockerfile").write_text("stub", encoding="utf-8")
                contexts[(base.name, arch)] = ctx
        return contexts

    monkeypatch.setattr(planner, "_render_nightly_contexts", fake_render_nightly)

    plan = build_plan(
        image_name="zxilly/cangjie",
        include_nightly=True,
        versions_root=tmp_path,
        existing_tags=set(),
        nightly_release=sample_nightly_release(),
        nightly_context_root=nightly_ctx,
    )

    nightly_releases = [r for r in plan.publish_matrix if r.channel == "nightly"]
    assert nightly_releases, "expected at least one nightly release"
    first = next(r for r in nightly_releases if r.base == "bookworm")
    assert first.tags[:4] == (
        "nightly-1.1.0-alpha.20260306010001",
        "nightly-1.1.0-alpha.20260306010001-bookworm",
        "nightly",
        "nightly-bookworm",
    )
    builds = [b for b in plan.build_matrix if b.release_id == first.release_id]
    assert {b.arch for b in builds} == {"amd64", "arm64"}


def test_build_plan_only_uses_present_nightly_assets(tmp_path, monkeypatch) -> None:
    def fake_render(release, platforms, output_root, bases=None):
        selected = bases if bases is not None else tuple()
        contexts = {}
        for base in selected:
            ctx = output_root / f"nightly-{release.tag_name}-{base.name}-amd64"
            ctx.mkdir(parents=True, exist_ok=True)
            (ctx / "Dockerfile").write_text("stub", encoding="utf-8")
            contexts[(base.name, "amd64")] = ctx
        return contexts

    monkeypatch.setattr(planner, "_render_nightly_contexts", fake_render)

    plan = build_plan(
        image_name="zxilly/cangjie",
        include_nightly=True,
        versions_root=tmp_path,
        existing_tags=set(),
        nightly_release=sample_nightly_release(include_arm64=False),
        nightly_context_root=tmp_path / "ctx",
    )

    nightly = next(r for r in plan.publish_matrix if r.channel == "nightly")
    assert nightly.arches == ("amd64",)
    builds = [b for b in plan.build_matrix if b.release_id == nightly.release_id]
    assert {b.arch for b in builds} == {"amd64"}


def test_build_plan_continues_when_nightly_lookup_fails(tmp_path, monkeypatch) -> None:
    _write_dockerfile(tmp_path, "lts", "1.0.5", "bookworm")
    monkeypatch.setattr(
        planner,
        "fetch_latest_nightly",
        lambda **_: (None, "nightly API request failed with HTTP 502"),
    )
    plan = build_plan(
        image_name="zxilly/cangjie",
        include_nightly=True,
        versions_root=tmp_path,
        existing_tags=set(),
    )
    assert plan.skipped_nightly_reason == "nightly API request failed with HTTP 502"
    assert any(release.channel == "lts" for release in plan.publish_matrix)


def test_fetch_latest_nightly_is_best_effort(monkeypatch) -> None:
    request = httpx.Request("GET", "https://example.com/nightly")
    response = httpx.Response(502, request=request)

    def raise_http_status_error(*args, **kwargs):
        raise httpx.HTTPStatusError("bad gateway", request=request, response=response)

    monkeypatch.setenv("TEST_NIGHTLY_TOKEN", "secret")
    monkeypatch.setattr(planner, "get_json", raise_http_status_error)

    release, reason = planner.fetch_latest_nightly(
        include_nightly=True,
        api_url="https://example.com/nightly",
        token_env="TEST_NIGHTLY_TOKEN",
    )

    assert release is None
    assert reason == "nightly API request failed with HTTP 502"


def test_fetch_latest_nightly_handles_invalid_json(monkeypatch) -> None:
    def raise_invalid_json(*args, **kwargs):
        raise json.JSONDecodeError("Expecting value", "<html>", 0)

    monkeypatch.setenv("TEST_NIGHTLY_TOKEN", "secret")
    monkeypatch.setattr(planner, "get_json", raise_invalid_json)

    release, reason = planner.fetch_latest_nightly(
        include_nightly=True,
        api_url="https://example.com/nightly",
        token_env="TEST_NIGHTLY_TOKEN",
    )

    assert release is None
    assert reason is not None
    assert reason.startswith("nightly API returned invalid JSON:")


def test_merge_release_manifests_requires_all_expected_arches(tmp_path, monkeypatch) -> None:
    digests_dir = tmp_path / "digests"
    write_digest_metadata(
        output_dir=digests_dir,
        release_id="lts-1-0-5-bookworm",
        arch="amd64",
        digest="sha256:amd64",
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        planner.subprocess,
        "run",
        lambda command, check: calls.append(command),
    )

    with pytest.raises(FileNotFoundError, match="arm64"):
        merge_release_manifests(
            image_name="zxilly/cangjie",
            release_id="lts-1-0-5-bookworm",
            tags=["1.0.5"],
            arches=["amd64", "arm64"],
            digests_dir=digests_dir,
        )

    assert calls == []


def test_merge_release_manifests_rejects_unexpected_arch_metadata(tmp_path) -> None:
    digests_dir = tmp_path / "digests"
    write_digest_metadata(
        output_dir=digests_dir,
        release_id="lts-1-0-5-bookworm",
        arch="amd64",
        digest="sha256:amd64",
    )
    write_digest_metadata(
        output_dir=digests_dir,
        release_id="lts-1-0-5-bookworm",
        arch="ppc64le",
        digest="sha256:ppc64le",
    )

    with pytest.raises(ValueError, match="unexpected digest metadata arch"):
        merge_release_manifests(
            image_name="zxilly/cangjie",
            release_id="lts-1-0-5-bookworm",
            tags=["1.0.5"],
            arches=["amd64", "arm64"],
            digests_dir=digests_dir,
        )
