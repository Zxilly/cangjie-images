from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cangjie_images.config import ARCH_VARIANTS, BASE_VARIANTS, STABLE_CHANNELS, Arch, StableChannel
from cangjie_images.models import StableManifest
from cangjie_images.planner import fetch_manifest
from cangjie_images.prepare import capture_sources
from cangjie_images.templates import render_dockerfile


@dataclass(frozen=True, slots=True)
class GenerationTarget:
    channel: StableChannel
    version: str
    base: str
    arch: Arch
    path: Path


@dataclass(slots=True)
class GenerationResult:
    written: list[GenerationTarget] = field(default_factory=list)
    skipped_existing: list[GenerationTarget] = field(default_factory=list)
    skipped_no_sources: list[GenerationTarget] = field(default_factory=list)


def _target_path(
    versions_root: Path,
    channel: StableChannel,
    version: str,
    base: str,
    arch: Arch,
) -> Path:
    return versions_root / channel / version / base / arch / "Dockerfile"


def _should_write(path: Path, *, force: bool, force_version: str | None, version: str) -> bool:
    if not path.exists():
        return True
    if force:
        return True
    return force_version is not None and force_version == version


def generate(
    *,
    versions_root: Path,
    manifest: StableManifest | dict[str, Any] | None = None,
    force: bool = False,
    force_version: str | None = None,
    run_smoke_test: bool = True,
) -> GenerationResult:
    """Generate committed Dockerfiles under ``versions_root/<channel>/<version>/<base>/<arch>/``.

    Existing files are left alone unless ``force`` or ``force_version`` match.
    Nightly is not part of this flow; nightly still uses the dynamic pipeline.
    """
    if manifest is None:
        manifest = fetch_manifest()
    elif not isinstance(manifest, StableManifest):
        manifest = StableManifest.model_validate(manifest)

    result = GenerationResult()

    for channel_name in STABLE_CHANNELS:
        channel = manifest.channels.get(channel_name)
        if channel is None:
            continue
        for version, platforms in channel.versions.items():
            pending: list[tuple[Any, GenerationTarget]] = []
            for base in BASE_VARIANTS:
                for arch_variant in ARCH_VARIANTS:
                    target = GenerationTarget(
                        channel=channel_name,
                        version=version,
                        base=base.name,
                        arch=arch_variant.name,
                        path=_target_path(
                            versions_root,
                            channel_name,
                            version,
                            base.name,
                            arch_variant.name,
                        ),
                    )
                    if _should_write(
                        target.path,
                        force=force,
                        force_version=force_version,
                        version=version,
                    ):
                        pending.append((base, target))
                    else:
                        result.skipped_existing.append(target)

            if not pending:
                continue

            sources = capture_sources(platforms, run_smoke_test=run_smoke_test)
            if not sources:
                for _, target in pending:
                    result.skipped_no_sources.append(target)
                continue

            source_by_arch = {s.arch: s for s in sources}
            for base, target in pending:
                source = source_by_arch.get(target.arch)
                if source is None:
                    result.skipped_no_sources.append(target)
                    continue
                target.path.parent.mkdir(parents=True, exist_ok=True)
                target.path.write_text(
                    render_dockerfile(
                        base_name=base.name,
                        base_image=base.image,
                        base_family=base.family,
                        channel=channel_name,
                        version=version,
                        arch=target.arch,
                        source=source,
                        slim=base.slim,
                    ),
                    encoding="utf-8",
                )
                result.written.append(target)

    return result
