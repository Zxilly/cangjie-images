from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import httpx
from pydantic import ValidationError

from cangjie_images.config import (
    ARCH_VARIANTS,
    BASE_VARIANTS,
    DEFAULT_IMAGE_NAME,
    DOCKER_HUB_PAGE_SIZE,
    NIGHTLY_RELEASE_API_URL,
    NIGHTLY_TOKEN_ENV,
    STABLE_CHANNELS,
    STABLE_MANIFEST_URL,
    Arch,
    BaseFamily,
    Channel,
    StableChannel,
)
from cangjie_images.http_client import get_json, http_client
from cangjie_images.models import (
    DigestMetadata,
    DockerHubImage,
    DockerHubTagPage,
    NightlyRelease,
    PlatformArtifact,
    StableManifest,
)
from cangjie_images.prepare import ArchSource, capture_sources
from cangjie_images.templates import render_dockerfile

STABLE_VERSION_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
SLUG_RE = re.compile(r"[^a-z0-9]+")
_SUPPORTED_ARCHES: frozenset[Arch] = frozenset(arch.name for arch in ARCH_VARIANTS)
_BASE_BY_NAME = {base.name: base for base in BASE_VARIANTS}
_ARCH_BY_NAME = {arch.name: arch for arch in ARCH_VARIANTS}
_VERSIONS_DIRNAME = "versions"
_NIGHTLY_CONTEXT_ROOT = ".build-context"


@dataclass(frozen=True, slots=True)
class PlannedBuild:
    release_id: str
    cache_scope: str
    arch: Arch
    runner: str
    platform: str
    base: str
    base_family: BaseFamily
    base_image: str
    channel: Channel
    version: str
    context_dir: str

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
            "context_dir": self.context_dir,
        }


@dataclass(frozen=True, slots=True)
class PlannedRelease:
    release_id: str
    channel: Channel
    version: str
    base: str
    tags: tuple[str, ...]
    arches: tuple[Arch, ...]

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


def fetch_existing_tags(image_name: str) -> dict[str, dict[str, str]]:
    namespace, repository = image_name.lower().split("/", 1)
    next_url: str | None = (
        f"https://hub.docker.com/v2/repositories/{namespace}/{repository}/tags"
        f"?page_size={DOCKER_HUB_PAGE_SIZE}"
    )
    tags: dict[str, dict[str, str]] = {}

    with http_client() as client:
        first_page = True
        while next_url:
            payload = get_json(client, next_url, allow_404=first_page)
            first_page = False
            if payload is None:
                return {}
            page = DockerHubTagPage.model_validate(payload)
            for item in page.results:
                if item.name:
                    tags[item.name] = _docker_hub_tag_state(item.images)
            next_url = page.next

    return tags


def fetch_latest_nightly(
    *,
    include_nightly: bool,
    api_url: str = NIGHTLY_RELEASE_API_URL,
    token_env: str = NIGHTLY_TOKEN_ENV,
) -> tuple[NightlyRelease | None, str | None]:
    if not include_nightly:
        return None, None

    token = os.getenv(token_env, "").strip()
    if not token:
        return None, f"{token_env} is not configured"

    try:
        with http_client() as client:
            payload = get_json(client, api_url, headers={"PRIVATE-TOKEN": token})
    except httpx.HTTPStatusError as exc:
        return None, f"nightly API request failed with HTTP {exc.response.status_code}"
    except httpx.HTTPError as exc:
        return None, f"nightly API request failed: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"nightly API returned invalid JSON: {exc}"

    try:
        release = NightlyRelease.model_validate(payload)
    except ValidationError as exc:
        return None, (
            "nightly API response did not include the expected release assets "
            f"({exc.error_count()} validation errors)"
        )
    return release, None


def parse_stable_version(version: str) -> tuple[int, int, int] | None:
    match = STABLE_VERSION_RE.match(version)
    if not match:
        return None
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )


def _version_sort_key(version: str) -> tuple[int, tuple[int, int, int], str]:
    parsed = parse_stable_version(version)
    if parsed is None:
        return (1, (0, 0, 0), version)
    return (0, parsed, version)


@dataclass(frozen=True, slots=True)
class CommittedDockerfile:
    channel: StableChannel
    version: str
    base: str
    arch: Arch
    context_dir: Path


def scan_committed_versions(versions_root: Path) -> list[CommittedDockerfile]:
    """Scan ``versions/<channel>/<version>/<base>/<arch>/Dockerfile`` entries.

    Returns one record per Dockerfile — arch is taken from the directory name.
    """
    if not versions_root.is_dir():
        return []

    found: list[CommittedDockerfile] = []
    for channel_dir in sorted(versions_root.iterdir()):
        if not channel_dir.is_dir() or channel_dir.name not in STABLE_CHANNELS:
            continue
        for version_dir in sorted(channel_dir.iterdir()):
            if not version_dir.is_dir():
                continue
            for base_dir in sorted(version_dir.iterdir()):
                if not base_dir.is_dir() or base_dir.name not in _BASE_BY_NAME:
                    continue
                for arch_dir in sorted(base_dir.iterdir()):
                    if not arch_dir.is_dir() or arch_dir.name not in _ARCH_BY_NAME:
                        continue
                    if not (arch_dir / "Dockerfile").is_file():
                        continue
                    found.append(
                        CommittedDockerfile(
                            channel=cast(StableChannel, channel_dir.name),
                            version=version_dir.name,
                            base=base_dir.name,
                            arch=cast(Arch, arch_dir.name),
                            context_dir=arch_dir,
                        )
                    )
    return found


def _compute_stable_heads(
    committed: list[CommittedDockerfile],
) -> tuple[str, str, dict[str, tuple[str, ...]]]:
    """Derive latest_lts, latest_sts, and minor_aliases from committed files."""
    latest_by_channel: dict[str, tuple[tuple[int, int, int], str]] = {}
    latest_by_series: dict[str, tuple[tuple[int, int, int], str, str]] = {}

    for entry in committed:
        parsed = parse_stable_version(entry.version)
        if parsed is None:
            continue
        current_ch = latest_by_channel.get(entry.channel)
        if current_ch is None or parsed > current_ch[0]:
            latest_by_channel[entry.channel] = (parsed, entry.version)

        series = f"{parsed[0]}.{parsed[1]}"
        current = latest_by_series.get(series)
        if (
            current is None
            or parsed > current[0]
            or (parsed == current[0] and current[2] != "lts" and entry.channel == "lts")
        ):
            latest_by_series[series] = (parsed, entry.version, entry.channel)

    aliases: dict[str, list[str]] = {}
    for series, (_, version, _) in latest_by_series.items():
        aliases.setdefault(version, []).append(series)
    minor_aliases = {v: tuple(sorted(ss)) for v, ss in aliases.items()}

    latest_lts = latest_by_channel.get("lts", ((0, 0, 0), ""))[1]
    latest_sts = latest_by_channel.get("sts", ((0, 0, 0), ""))[1]
    return latest_lts, latest_sts, minor_aliases


def nightly_download_info(release: NightlyRelease | dict[str, Any]) -> dict[str, PlatformArtifact]:
    if not isinstance(release, NightlyRelease):
        release = NightlyRelease.model_validate(release)

    version = release.tag_name
    assets_by_name = {asset.name: asset.browser_download_url for asset in release.assets}
    info: dict[str, PlatformArtifact] = {}
    for arch in ARCH_VARIANTS:
        filename = f"cangjie-sdk-linux-{arch.nightly_arch}-{version}.tar.gz"
        url = assets_by_name.get(filename)
        if not url:
            continue
        info[arch.manifest_key] = PlatformArtifact(url=url, sha256="", name=filename)
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
    channel: Channel,
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


def _docker_hub_tag_state(images: list[DockerHubImage]) -> dict[str, str]:
    state: dict[str, str] = {}
    for image in images:
        arch = image.architecture.lower()
        if image.os.lower() != "linux" or arch not in _SUPPORTED_ARCHES:
            continue
        if arch not in state or image.digest:
            state[arch] = image.digest
    return state


def _normalize_tag_state(state: AbstractSet[str] | Mapping[str, str]) -> dict[str, str]:
    if isinstance(state, Mapping):
        return {
            arch.lower(): digest
            for arch, digest in state.items()
            if arch.lower() in _SUPPORTED_ARCHES
        }
    return {arch.lower(): "" for arch in state if arch.lower() in _SUPPORTED_ARCHES}


def _normalize_existing_tags(
    existing_tags: AbstractSet[str] | Mapping[str, AbstractSet[str] | Mapping[str, str]],
) -> dict[str, dict[str, str]]:
    if isinstance(existing_tags, AbstractSet):
        assumed_state: dict[str, str] = {arch: "" for arch in _SUPPORTED_ARCHES}
        return {tag: dict(assumed_state) for tag in existing_tags}
    return {tag: _normalize_tag_state(state) for tag, state in existing_tags.items()}


def _expected_tag_state(
    tag: str,
    expected_arches: tuple[str, ...],
    existing_tags: dict[str, dict[str, str]],
) -> dict[str, str] | None:
    state = existing_tags.get(tag)
    if state is None:
        return None
    if any(arch not in state for arch in expected_arches):
        return None
    return {arch: state[arch] for arch in expected_arches}


def _is_release_complete(
    tags: tuple[str, ...],
    expected_arches: tuple[str, ...],
    existing_tags: dict[str, dict[str, str]],
) -> bool:
    if not expected_arches:
        return False
    reference = _expected_tag_state(tags[0], expected_arches, existing_tags)
    if reference is None:
        return False
    for tag in tags[1:]:
        if _expected_tag_state(tag, expected_arches, existing_tags) != reference:
            return False
    return True


def _plan_build_entry(
    *,
    release_id: str,
    channel: Channel,
    version: str,
    base_name: str,
    base_family: BaseFamily,
    base_image: str,
    arch_name: Arch,
    context_dir: str,
) -> PlannedBuild:
    arch = _ARCH_BY_NAME[arch_name]
    return PlannedBuild(
        release_id=release_id,
        cache_scope=slugify(f"{base_name}-{arch.name}"),
        arch=arch.name,
        runner=arch.runner,
        platform=arch.platform,
        base=base_name,
        base_family=base_family,
        base_image=base_image,
        channel=channel,
        version=version,
        context_dir=context_dir,
    )


def _render_nightly_contexts(
    nightly_release: NightlyRelease,
    platforms: dict[str, PlatformArtifact],
    output_root: Path,
    bases: tuple[Any, ...] | None = None,
) -> dict[tuple[str, Arch], Path]:
    """Render nightly Dockerfiles per (base, arch) under ``output_root``.

    Probes SDK layout once per arch and writes ``<output_root>/<slug>/Dockerfile``
    for every (base, arch) combination. Returns {(base_name, arch): context_dir}.
    """
    selected = bases if bases is not None else BASE_VARIANTS
    if not selected:
        return {}

    sources: list[ArchSource] = capture_sources(platforms, run_smoke_test=True)
    if not sources:
        return {}

    version = nightly_release.tag_name
    contexts: dict[tuple[str, Arch], Path] = {}
    for base in selected:
        for source in sources:
            context = output_root / slugify(f"nightly-{version}-{base.name}-{source.arch}")
            context.mkdir(parents=True, exist_ok=True)
            (context / "Dockerfile").write_text(
                render_dockerfile(
                    base_name=base.name,
                    base_image=base.image,
                    base_family=base.family,
                    channel="nightly",
                    version=version,
                    arch=source.arch,
                    source=source,
                    slim=base.slim,
                ),
                encoding="utf-8",
            )
            contexts[(base.name, source.arch)] = context
    return contexts


def build_plan(
    *,
    image_name: str = DEFAULT_IMAGE_NAME,
    include_nightly: bool = False,
    force: bool = False,
    versions_root: Path | None = None,
    existing_tags: AbstractSet[str]
    | Mapping[str, AbstractSet[str] | Mapping[str, str]]
    | None = None,
    nightly_release: NightlyRelease | dict[str, Any] | None = None,
    skipped_nightly_reason: str | None = None,
    nightly_context_root: Path | None = None,
) -> PlanResult:
    if versions_root is None:
        versions_root = Path(_VERSIONS_DIRNAME)
    if nightly_context_root is None:
        nightly_context_root = Path(_NIGHTLY_CONTEXT_ROOT)

    existing_tags = (
        _normalize_existing_tags(existing_tags)
        if existing_tags is not None
        else fetch_existing_tags(image_name)
    )

    if nightly_release is not None and not isinstance(nightly_release, NightlyRelease):
        nightly_release = NightlyRelease.model_validate(nightly_release)
    if include_nightly and nightly_release is None and skipped_nightly_reason is None:
        nightly_release, skipped_nightly_reason = fetch_latest_nightly(include_nightly=True)
    nightly_version = nightly_release.tag_name if nightly_release else None

    committed = scan_committed_versions(versions_root)
    latest_lts, latest_sts, minor_aliases = _compute_stable_heads(committed)

    planned_builds: list[PlannedBuild] = []
    planned_releases: list[PlannedRelease] = []

    # Stable releases: group per-arch CommittedDockerfile records by
    # (channel, version, base) and emit one PlannedRelease per group.
    stable_groups: dict[tuple[StableChannel, str, str], list[CommittedDockerfile]] = {}
    for entry in committed:
        stable_groups.setdefault((entry.channel, entry.version, entry.base), []).append(entry)

    for (channel, version, base_name), entries in stable_groups.items():
        base = _BASE_BY_NAME[base_name]
        arches: tuple[Arch, ...] = tuple(e.arch for e in entries)
        tags = build_tags(
            channel=channel,
            version=version,
            base_name=base_name,
            default_base=base.default,
            latest_lts=latest_lts,
            latest_sts=latest_sts,
            minor_aliases=minor_aliases,
        )
        release_id = slugify(f"{channel}-{version}-{base_name}")
        if not force and _is_release_complete(tags, arches, existing_tags):
            continue
        for entry in entries:
            planned_builds.append(
                _plan_build_entry(
                    release_id=release_id,
                    channel=channel,
                    version=version,
                    base_name=base_name,
                    base_family=base.family,
                    base_image=base.image,
                    arch_name=entry.arch,
                    context_dir=str(entry.context_dir),
                )
            )
        planned_releases.append(
            PlannedRelease(
                release_id=release_id,
                channel=channel,
                version=version,
                base=base_name,
                tags=tags,
                arches=arches,
            )
        )

    # Nightly: dynamic render at plan time, only if at least one base needs
    # a build (avoids a ~1GB SDK download when every nightly tag already
    # matches what Docker Hub has).
    if nightly_release is not None:
        platforms = nightly_download_info(nightly_release)
        if not platforms:
            skipped_nightly_reason = (
                skipped_nightly_reason
                or f"nightly release {nightly_release.tag_name} has no supported assets"
            )
        else:
            nightly_arches: tuple[Arch, ...] = tuple(
                arch.name for arch in ARCH_VARIANTS if arch.manifest_key in platforms
            )
            pending: list[tuple[Any, tuple[str, ...], str]] = []
            for base in BASE_VARIANTS:
                tags = build_tags(
                    channel="nightly",
                    version=nightly_release.tag_name,
                    base_name=base.name,
                    default_base=base.default,
                    latest_lts=latest_lts,
                    latest_sts=latest_sts,
                    minor_aliases=minor_aliases,
                )
                release_id = slugify(f"nightly-{nightly_release.tag_name}-{base.name}")
                if not force and _is_release_complete(tags, nightly_arches, existing_tags):
                    continue
                pending.append((base, tags, release_id))

            if pending:
                contexts = _render_nightly_contexts(
                    nightly_release,
                    platforms,
                    nightly_context_root,
                    bases=tuple(base for base, _, _ in pending),
                )
                if not contexts:
                    skipped_nightly_reason = (
                        skipped_nightly_reason
                        or f"nightly release {nightly_release.tag_name} has no capturable SDK"
                    )
                else:
                    for base, tags, release_id in pending:
                        present_arches: tuple[Arch, ...] = tuple(
                            arch for arch in nightly_arches if (base.name, arch) in contexts
                        )
                        if not present_arches:
                            continue
                        for arch_name in present_arches:
                            planned_builds.append(
                                _plan_build_entry(
                                    release_id=release_id,
                                    channel="nightly",
                                    version=nightly_release.tag_name,
                                    base_name=base.name,
                                    base_family=base.family,
                                    base_image=base.image,
                                    arch_name=arch_name,
                                    context_dir=str(contexts[(base.name, arch_name)]),
                                )
                            )
                        planned_releases.append(
                            PlannedRelease(
                                release_id=release_id,
                                channel="nightly",
                                version=nightly_release.tag_name,
                                base=base.name,
                                tags=tags,
                                arches=present_arches,
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
    metadata = DigestMetadata(release_id=release_id, arch=arch, digest=digest)
    path.write_text(metadata.model_dump_json(indent=2) + "\n", encoding="utf-8")
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
    if not arches:
        raise ValueError(f"no arches provided for release_id={release_id}")

    refs_by_arch: dict[str, str] = {}
    expected_arches = set(arches)
    for path in sorted(digests_dir.glob(f"{release_id}-*.json")):
        metadata = DigestMetadata.model_validate_json(path.read_text(encoding="utf-8"))
        if metadata.release_id != release_id:
            raise ValueError(
                f"digest metadata release_id mismatch: expected {release_id}, got {metadata.release_id}"
            )
        if metadata.arch in refs_by_arch:
            raise ValueError(f"duplicate digest metadata found for {release_id}/{metadata.arch}")
        if metadata.arch not in expected_arches:
            raise ValueError(f"unexpected digest metadata arch for {release_id}: {metadata.arch}")
        refs_by_arch[metadata.arch] = f"{image_name}@{metadata.digest}"

    missing_arches = [arch for arch in arches if arch not in refs_by_arch]
    if missing_arches:
        raise FileNotFoundError(
            f"missing digest metadata for {release_id}: {', '.join(missing_arches)}"
        )
    digest_refs = [refs_by_arch[arch] for arch in arches]

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
