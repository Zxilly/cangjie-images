from __future__ import annotations

import pytest
from pydantic import ValidationError

from cangjie_images.planner import build_plan, build_tags, compute_minor_alias_targets


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
        nightly_version=None,
        skipped_nightly_reason=None,
    )

    release_ids = {release.release_id for release in plan.publish_matrix}
    assert "lts-1-0-5-bookworm" not in release_ids
    assert "lts-1-0-4-bookworm" in release_ids


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
        nightly_version="1.1.0-alpha.20260306010001",
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

