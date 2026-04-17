from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from cangjie_images.config import (
    ARCH_VARIANTS,
    BASE_VARIANTS,
    DEFAULT_IMAGE_NAME,
    DOCKER_HUB_PAGE_SIZE,
    NIGHTLY_DOWNLOAD_BASE_URL,
    NIGHTLY_RELEASE_API_URL,
    NIGHTLY_TOKEN_ENV,
    STABLE_MANIFEST_URL,
)
from cangjie_images.http_client import get_json, http_client
from cangjie_images.models import (
    DigestMetadata,
    DockerHubTagPage,
    NightlyRelease,
    PlatformArtifact,
    StableManifest,
)

STABLE_VERSION_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class PlannedBuild:
    release_id: str
    cache_scope: str
    arch: str
    runner: str
    platform: str
    base: str
    base_family: str
    base_image: str
    channel: str
    version: str
    archive_url: str
    archive_sha256: str
    native_dir: str

    def as_dict(self) -> dict[str, str]:
        return {
            "release_id": self.release_id,
            "cache_scope": self.cache_scope,
            "arch": self.arch,
            "runner": self.runner,
            "platform": self.platform,
            "base": self.base,
            "base_family": self.base_family,
            "base_image": self.base_image,
            "channel": self.channel,
            "version": self.version,
            "archive_url": self.archive_url,
            "archive_sha256": self.archive_sha256,
            "native_dir": self.native_dir,
        }


@dataclass(frozen=True, slots=True)
class PlannedRelease:
    release_id: str
    channel: str
    version: str
    base: str
    tags: tuple[str, ...]
    arches: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "channel": self.channel,
            "version": self.version,
            "base": self.base,
            "arches_json": json.dumps(list(self.arches)),
            "tags_json": json.dumps(list(self.tags)),
        }


@dataclass(frozen=True, slots=True)
class PlanResult:
    image: str
    existing_tag_count: int
    build_matrix: tuple[PlannedBuild, ...]
    publish_matrix: tuple[PlannedRelease, ...]
    nightly_version: str | None
    skipped_nightly_reason: str | None

    @property
    def has_work(self) -> bool:
        return bool(self.publish_matrix)

    def as_json(self) -> str:
        payload = {
            "image": self.image,
            "existing_tag_count": self.existing_tag_count,
            "nightly_version": self.nightly_version,
            "skipped_nightly_reason": self.skipped_nightly_reason,
            "has_work": self.has_work,
            "build_matrix": [entry.as_dict() for entry in self.build_matrix],
            "publish_matrix": [entry.as_dict() for entry in self.publish_matrix],
        }
        return json.dumps(payload, indent=2, sort_keys=True)

    def summary_lines(self) -> list[str]:
        lines = [
            "## Publish Plan",
            "",
            f"- Image: `{self.image}`",
            f"- Existing Docker Hub tags observed: `{self.existing_tag_count}`",
            f"- Pending release variants: `{len(self.publish_matrix)}`",
            f"- Pending platform builds: `{len(self.build_matrix)}`",
        ]
        if self.nightly_version:
            lines.append(f"- Nightly version: `{self.nightly_version}`")
        if self.skipped_nightly_reason:
            lines.append(f"- Nightly skipped: {self.skipped_nightly_reason}")
        if self.publish_matrix:
            lines.extend(["", "### Pending Variants", ""])
            for release in self.publish_matrix:
                lines.append(
                    f"- `{release.release_id}` -> `{', '.join(release.tags[:4])}`"
                    + (" ..." if len(release.tags) > 4 else "")
                )
        else:
            lines.extend(["", "Nothing to publish."])
        return lines


def fetch_manifest(url: str = STABLE_MANIFEST_URL) -> StableManifest:
    with http_client() as client:
        payload = get_json(client, url)
    return StableManifest.model_validate(payload)


def fetch_existing_tags(image_name: str) -> set[str]:
    namespace, repository = image_name.lower().split("/", 1)
    next_url: str | None = (
        f"https://hub.docker.com/v2/repositories/{namespace}/{repository}/tags"
        f"?page_size={DOCKER_HUB_PAGE_SIZE}"
    )
    tags: set[str] = set()

    with http_client() as client:
        first_page = True
        while next_url:
            payload = get_json(client, next_url, allow_404=first_page)
            first_page = False
            if payload is None:
                return set()
            page = DockerHubTagPage.model_validate(payload)
            for item in page.results:
                if item.name:
                    tags.add(item.name)
            next_url = page.next

    return tags


def fetch_latest_nightly(
    *,
    include_nightly: bool,
    api_url: str = NIGHTLY_RELEASE_API_URL,
    token_env: str = NIGHTLY_TOKEN_ENV,
) -> tuple[str | None, str | None]:
    if not include_nightly:
        return None, None

    token = os.getenv(token_env, "").strip()
    if not token:
        return None, f"{token_env} is not configured"

    try:
        with http_client() as client:
            payload = get_json(client, api_url, headers={"PRIVATE-TOKEN": token})
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"nightly API request failed with HTTP {exc.response.status_code}") from exc

    release = NightlyRelease.model_validate(payload)
    return release.tag_name, None


def parse_stable_version(version: str) -> tuple[int, int, int] | None:
    match = STABLE_VERSION_RE.match(version)
    if not match:
        return None
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )


def compute_minor_alias_targets(manifest: StableManifest | dict[str, Any]) -> dict[str, tuple[str, ...]]:
    if not isinstance(manifest, StableManifest):
        manifest = StableManifest.model_validate(manifest)
    latest_by_series: dict[str, tuple[tuple[int, int, int], str, str]] = {}

    for channel in ("lts", "sts"):
        versions = manifest.channels[channel].versions
        for version in versions:
            parsed = parse_stable_version(version)
            if parsed is None:
                continue
            series = f"{parsed[0]}.{parsed[1]}"
            current = latest_by_series.get(series)
            if current is None:
                latest_by_series[series] = (parsed, version, channel)
                continue
            current_parsed, _, current_channel = current
            if parsed > current_parsed:
                latest_by_series[series] = (parsed, version, channel)
            elif parsed == current_parsed and current_channel != "lts" and channel == "lts":
                latest_by_series[series] = (parsed, version, channel)

    aliases: dict[str, list[str]] = {}
    for series, (_, version, _) in latest_by_series.items():
        aliases.setdefault(version, []).append(series)

    return {version: tuple(sorted(serieses)) for version, serieses in aliases.items()}


def nightly_download_info(version: str) -> dict[str, PlatformArtifact]:
    info: dict[str, PlatformArtifact] = {}
    for arch in ARCH_VARIANTS:
        filename = f"cangjie-sdk-linux-{arch.nightly_arch}-{version}.tar.gz"
        info[arch.manifest_key] = PlatformArtifact(
            url=f"{NIGHTLY_DOWNLOAD_BASE_URL}/{version}/{filename}",
            sha256="",
            name=filename,
        )
    return info


def slugify(value: str) -> str:
    return SLUG_RE.sub("-", value.lower()).strip("-")


def _base_tag_names(base_name: str, *, default: bool, raw_tag: str) -> list[str]:
    tags = [f"{raw_tag}-{base_name}"]
    if default:
        tags.insert(0, raw_tag)
    return tags


def build_tags(
    *,
    channel: str,
    version: str,
    base_name: str,
    default_base: bool,
    latest_lts: str,
    latest_sts: str,
    minor_aliases: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    raw_tags: list[str] = []

    if channel == "nightly":
        raw_tags.append(f"nightly-{version}")
        raw_tags.append("nightly")
    else:
        raw_tags.append(version)
        raw_tags.extend(minor_aliases.get(version, ()))
        if channel == "lts" and version == latest_lts:
            raw_tags.extend(["lts", "latest"])
        if channel == "sts" and version == latest_sts:
            raw_tags.append("sts")

    tags: list[str] = []
    for raw_tag in raw_tags:
        tags.extend(_base_tag_names(base_name, default=default_base, raw_tag=raw_tag))

    return tuple(dict.fromkeys(tags))


def _stable_release_sources(
    manifest: StableManifest,
) -> list[tuple[str, str, dict[str, PlatformArtifact]]]:
    releases: list[tuple[str, str, dict[str, PlatformArtifact]]] = []
    for channel in ("lts", "sts"):
        versions = manifest.channels[channel].versions

        def sort_key(version: str) -> tuple[int, tuple[int, int, int], str]:
            parsed = parse_stable_version(version)
            if parsed is None:
                return (1, (0, 0, 0), version)
            return (0, parsed, version)

        for version in sorted(versions, key=sort_key):
            releases.append((channel, version, versions[version]))
    return releases


def build_plan(
    *,
    image_name: str = DEFAULT_IMAGE_NAME,
    include_nightly: bool = False,
    force: bool = False,
    manifest: StableManifest | dict[str, Any] | None = None,
    existing_tags: set[str] | None = None,
    nightly_version: str | None = None,
    skipped_nightly_reason: str | None = None,
) -> PlanResult:
    if manifest is None:
        manifest = fetch_manifest()
    elif not isinstance(manifest, StableManifest):
        manifest = StableManifest.model_validate(manifest)
    existing_tags = existing_tags if existing_tags is not None else fetch_existing_tags(image_name)

    if include_nightly and nightly_version is None and skipped_nightly_reason is None:
        nightly_version, skipped_nightly_reason = fetch_latest_nightly(include_nightly=True)

    latest_lts = manifest.channels["lts"].latest
    latest_sts = manifest.channels["sts"].latest
    minor_aliases = compute_minor_alias_targets(manifest)

    planned_builds: list[PlannedBuild] = []
    planned_releases: list[PlannedRelease] = []

    release_sources = _stable_release_sources(manifest)
    if nightly_version:
        release_sources.append(("nightly", nightly_version, nightly_download_info(nightly_version)))

    for channel, version, platforms in release_sources:
        for base in BASE_VARIANTS:
            tags = build_tags(
                channel=channel,
                version=version,
                base_name=base.name,
                default_base=base.default,
                latest_lts=latest_lts,
                latest_sts=latest_sts,
                minor_aliases=minor_aliases,
            )
            if not force and set(tags).issubset(existing_tags):
                continue

            release_id = slugify(f"{channel}-{version}-{base.name}")
            release_arches: list[str] = []

            for arch in ARCH_VARIANTS:
                info = platforms.get(arch.manifest_key)
                if not info:
                    continue
                release_arches.append(arch.name)
                planned_builds.append(
                    PlannedBuild(
                        release_id=release_id,
                        cache_scope=slugify(f"{base.name}-{arch.name}"),
                        arch=arch.name,
                        runner=arch.runner,
                        platform=arch.platform,
                        base=base.name,
                        base_family=base.family,
                        base_image=base.image,
                        channel=channel,
                        version=version,
                        archive_url=info.url,
                        archive_sha256=info.sha256,
                        native_dir=arch.native_dir,
                    )
                )

            if release_arches:
                planned_releases.append(
                    PlannedRelease(
                        release_id=release_id,
                        channel=channel,
                        version=version,
                        base=base.name,
                        tags=tags,
                        arches=tuple(release_arches),
                    )
                )

    planned_builds.sort(key=lambda item: (item.channel, item.version, item.base, item.arch))
    planned_releases.sort(key=lambda item: (item.channel, item.version, item.base))

    return PlanResult(
        image=image_name,
        existing_tag_count=len(existing_tags),
        build_matrix=tuple(planned_builds),
        publish_matrix=tuple(planned_releases),
        nightly_version=nightly_version,
        skipped_nightly_reason=skipped_nightly_reason,
    )


def write_github_outputs(plan: PlanResult, output_path: Path) -> None:
    payloads = {
        "has_work": "true" if plan.has_work else "false",
        "build_matrix": json.dumps([item.as_dict() for item in plan.build_matrix]),
        "publish_matrix": json.dumps([item.as_dict() for item in plan.publish_matrix]),
    }

    with output_path.open("a", encoding="utf-8") as handle:
        for name, value in payloads.items():
            delimiter = f"ghadelim_{uuid.uuid4().hex}"
            handle.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")


def write_summary(plan: PlanResult, summary_path: Path) -> None:
    summary_path.write_text("\n".join(plan.summary_lines()) + "\n", encoding="utf-8")


def write_digest_metadata(
    *,
    output_dir: Path,
    release_id: str,
    arch: str,
    digest: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{release_id}-{arch}.json"
    path.write_text(
        json.dumps(
            {
                "release_id": release_id,
                "arch": arch,
                "digest": digest,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def merge_release_manifests(
    *,
    image_name: str,
    release_id: str,
    tags: list[str],
    arches: list[str],
    digests_dir: Path,
    summary_path: Path | None = None,
) -> None:
    if not tags:
        raise ValueError(f"no tags provided for release_id={release_id}")

    digest_refs: list[str] = []
    for path in sorted(digests_dir.glob(f"{release_id}-*.json")):
        metadata = DigestMetadata.model_validate_json(path.read_text(encoding="utf-8"))
        digest_refs.append(f"{image_name}@{metadata.digest}")

    if not digest_refs:
        raise FileNotFoundError(f"no digest metadata found for release_id={release_id}")

    command = ["docker", "buildx", "imagetools", "create"]
    for tag in tags:
        command.extend(["-t", f"{image_name}:{tag}"])
    command.extend(digest_refs)
    subprocess.run(command, check=True)
    subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", f"{image_name}:{tags[0]}"],
        check=True,
    )

    if summary_path is not None:
        append_publish_summary(
            summary_path=summary_path,
            release_id=release_id,
            tags=tags,
            arches=arches,
        )


def append_publish_summary(
    *,
    summary_path: Path,
    release_id: str,
    tags: list[str],
    arches: list[str],
) -> None:
    preview = ", ".join(tags[:6]) + (" ..." if len(tags) > 6 else "")
    lines = [
        f"### Published `{release_id}`",
        "",
        f"- Tags: `{preview}`",
        f"- Architectures: `{', '.join(arches)}`",
        "",
    ]
    with summary_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

