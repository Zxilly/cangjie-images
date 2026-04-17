from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

import cangjie_images.planner as planner
from cangjie_images.planner import (
    build_plan,
    build_tags,
    compute_minor_alias_targets,
    merge_release_manifests,
    write_digest_metadata,
)


def sample_manifest() -> dict:
    return {
        "channels": {
            "lts": {
                "latest": "1.0.5",
                "versions": {
                    "1.0.4": {
                        "linux-x64": {"url": "https://example.com/1.0.4-amd64.tgz", "sha256": "a" * 64},
                        "linux-arm64": {"url": "https://example.com/1.0.4-arm64.tgz", "sha256": "b" * 64},
                    },
                    "1.0.5": {
                        "linux-x64": {"url": "https://example.com/1.0.5-amd64.tgz", "sha256": "c" * 64},
                        "linux-arm64": {"url": "https://example.com/1.0.5-arm64.tgz", "sha256": "d" * 64},
                    },
                },
            },
            "sts": {
                "latest": "1.1.0-beta.25",
                "versions": {
                    "0.53.18": {
                        "linux-x64": {"url": "https://example.com/0.53.18-amd64.tgz", "sha256": "e" * 64},
                        "linux-arm64": {"url": "https://example.com/0.53.18-arm64.tgz", "sha256": "f" * 64},
                    },
                    "1.1.0-beta.25": {
                        "linux-x64": {"url": "https://example.com/1.1.0b25-amd64.tgz", "sha256": "1" * 64},
                        "linux-arm64": {"url": "https://example.com/1.1.0b25-arm64.tgz", "sha256": "2" * 64},
                    },
                },
            },
        }
    }


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


def test_compute_minor_alias_targets_only_uses_stable_versions() -> None:
    aliases = compute_minor_alias_targets(sample_manifest())
    assert aliases["1.0.5"] == ("1.0",)
    assert aliases["0.53.18"] == ("0.53",)
    assert "1.1.0-beta.25" not in aliases


def test_build_tags_for_default_lts_base() -> None:
    tags = build_tags(
        channel="lts",
        version="1.0.5",
        base_name="bookworm",
        default_base=True,
        latest_lts="1.0.5",
        latest_sts="1.1.0-beta.25",
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


def test_build_plan_skips_release_when_all_tags_exist() -> None:
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
        manifest=sample_manifest(),
        existing_tags=existing_tags,
        skipped_nightly_reason=None,
    )

    release_ids = {release.release_id for release in plan.publish_matrix}
    assert "lts-1-0-5-bookworm" not in release_ids
    assert "lts-1-0-4-bookworm" in release_ids


def test_build_plan_keeps_release_when_existing_tags_are_missing_expected_arch() -> None:
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
        manifest=sample_manifest(),
        existing_tags=existing_tags,
    )

    release_ids = {release.release_id for release in plan.publish_matrix}
    assert "lts-1-0-5-bookworm" in release_ids


def test_build_plan_keeps_release_when_moving_aliases_are_stale() -> None:
    current_release = {"amd64": "sha256:new-amd64", "arm64": "sha256:new-arm64"}
    stale_alias = {"amd64": "sha256:old-amd64", "arm64": "sha256:old-arm64"}
    existing_tags = {
        "1.0.5": current_release,
        "1.0.5-bookworm": current_release,
        "1.0": current_release,
        "1.0-bookworm": current_release,
        "lts": stale_alias,
        "lts-bookworm": stale_alias,
        "latest": stale_alias,
        "latest-bookworm": stale_alias,
    }
    plan = build_plan(
        image_name="zxilly/cangjie",
        include_nightly=False,
        manifest=sample_manifest(),
        existing_tags=existing_tags,
    )

    release_ids = {release.release_id for release in plan.publish_matrix}
    assert "lts-1-0-5-bookworm" in release_ids


def test_build_plan_rejects_invalid_manifest() -> None:
    with pytest.raises(ValidationError):
        build_plan(
            image_name="zxilly/cangjie",
            include_nightly=False,
            manifest={"channels": {"lts": {"latest": 1.0, "versions": "oops"}}},
            existing_tags=set(),
        )


def test_build_plan_adds_nightly_tags() -> None:
    plan = build_plan(
        image_name="zxilly/cangjie",
        include_nightly=True,
        manifest=sample_manifest(),
        existing_tags=set(),
        nightly_release=sample_nightly_release(),
        skipped_nightly_reason=None,
    )

    nightly_release = next(
        release
        for release in plan.publish_matrix
        if release.channel == "nightly" and release.base == "bookworm"
    )
    assert nightly_release.tags[:4] == (
        "nightly-1.1.0-alpha.20260306010001",
        "nightly-1.1.0-alpha.20260306010001-bookworm",
        "nightly",
        "nightly-bookworm",
    )
    nightly_builds = [build for build in plan.build_matrix if build.release_id == nightly_release.release_id]
    assert {build.arch for build in nightly_builds} == {"amd64", "arm64"}


def test_build_plan_only_uses_present_nightly_assets() -> None:
    plan = build_plan(
        image_name="zxilly/cangjie",
        include_nightly=True,
        manifest=sample_manifest(),
        existing_tags=set(),
        nightly_release=sample_nightly_release(include_arm64=False),
    )

    nightly_release = next(
        release
        for release in plan.publish_matrix
        if release.channel == "nightly" and release.base == "bookworm"
    )
    assert nightly_release.arches == ("amd64",)
    nightly_builds = [build for build in plan.build_matrix if build.release_id == nightly_release.release_id]
    assert {build.arch for build in nightly_builds} == {"amd64"}


def test_build_plan_continues_when_nightly_lookup_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        planner,
        "fetch_latest_nightly",
        lambda **_: (None, "nightly API request failed with HTTP 502"),
    )

    plan = build_plan(
        image_name="zxilly/cangjie",
        include_nightly=True,
        manifest=sample_manifest(),
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
