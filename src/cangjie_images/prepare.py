from __future__ import annotations

import hashlib
import os
import subprocess
import tarfile
import tempfile
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from cangjie_images.config import ARCH_VARIANTS, Arch, ArchVariant
from cangjie_images.http_client import http_client, stream_download
from cangjie_images.models import PlatformArtifact

_BASELINE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_BASELINE_HOME = "/root"
_ENVSETUP_PATH_VAR = "_CANGJIE_ENVSETUP_SCRIPT"
_VOLATILE_ENV_KEYS: frozenset[str] = frozenset(
    {"PWD", "OLDPWD", "SHLVL", "_", "HOME", _ENVSETUP_PATH_VAR}
)
_PATH_LIKE_KEYS: frozenset[str] = frozenset(
    {"PATH", "LD_LIBRARY_PATH", "PKG_CONFIG_PATH", "CPATH", "LIBRARY_PATH", "MANPATH"}
)


@dataclass(frozen=True, slots=True)
class PathListDiff:
    prepend: tuple[str, ...]
    append: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not self.prepend and not self.append


@dataclass(frozen=True, slots=True)
class EnvDiff:
    assignments: dict[str, str]
    path_diffs: dict[str, PathListDiff]


@dataclass(frozen=True, slots=True)
class ArchSource:
    """SDK archive reference for a single architecture."""

    arch: Arch
    url: str
    sha256: str


def download_archive(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with http_client(timeout=None) as client, dest.open("wb") as handle:
        stream_download(client, url, handle)


def compute_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    actual = compute_sha256(path)
    if actual.lower() != expected.lower():
        raise RuntimeError(f"sha256 mismatch for {path}: expected {expected}, got {actual}")


def extract_archive(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(dest, filter="data")


def _split_path_list(value: str) -> tuple[str, ...]:
    return tuple(part for part in value.split(":") if part)


def _split_path_diff(before: str, after: str) -> PathListDiff:
    """Find where ``before`` sits inside ``after`` and return the surrounding entries.

    envsetup.sh typically does ``PATH=<prefix>:$PATH:<suffix>`` so the
    baseline appears as a contiguous subsequence in the new value. Preserving
    that structure lets the emitted Dockerfile ENV keep ``$PATH`` instead of
    baking the runner's baseline into the image.
    """

    old_entries = _split_path_list(before)
    new_entries = _split_path_list(after)
    if not old_entries:
        return PathListDiff(prepend=tuple(dict.fromkeys(new_entries)), append=())

    old_len = len(old_entries)
    for i in range(len(new_entries) - old_len + 1):
        if new_entries[i : i + old_len] == old_entries:
            return PathListDiff(
                prepend=tuple(dict.fromkeys(new_entries[:i])),
                append=tuple(dict.fromkeys(new_entries[i + old_len :])),
            )

    added = tuple(p for p in new_entries if p not in old_entries)
    return PathListDiff(prepend=tuple(dict.fromkeys(added)), append=())


def capture_envsetup(sdk_home_on_host: Path) -> EnvDiff:
    envsetup = sdk_home_on_host / "envsetup.sh"
    if not envsetup.is_file():
        raise FileNotFoundError(f"envsetup.sh not found under {sdk_home_on_host}")

    base_env = {
        "HOME": _BASELINE_HOME,
        "PATH": _BASELINE_PATH,
        _ENVSETUP_PATH_VAR: str(envsetup),
    }

    def _run(script: str) -> dict[str, str]:
        result = subprocess.run(
            ["bash", "--norc", "--noprofile", "-c", script],
            env=base_env,
            capture_output=True,
            check=True,
        )
        entries = result.stdout.split(b"\x00")
        out: dict[str, str] = {}
        for entry in entries:
            if not entry:
                continue
            key, _, value = entry.decode().partition("=")
            if key:
                out[key] = value
        return out

    before = _run("env -0")
    after = _run(f'. "${_ENVSETUP_PATH_VAR}" >/dev/null 2>&1; env -0')

    assignments: dict[str, str] = {}
    path_diffs: dict[str, PathListDiff] = {}

    for key, value in sorted(after.items()):
        if key in _VOLATILE_ENV_KEYS:
            continue
        if before.get(key) == value:
            continue
        if key in _PATH_LIKE_KEYS and key in before:
            diff = _split_path_diff(before[key], value)
            if diff.is_empty:
                continue
            path_diffs[key] = diff
        elif key in _PATH_LIKE_KEYS:
            cleaned = ":".join(_split_path_list(value))
            if cleaned:
                assignments[key] = cleaned
        else:
            assignments[key] = value

    return EnvDiff(assignments=assignments, path_diffs=path_diffs)


def rewrite_paths(diff: EnvDiff, host_prefix: str, image_prefix: str) -> EnvDiff:
    # envsetup.sh resolves CANGJIE_HOME via readlink of its own location,
    # so captured paths point at the host staging dir. Rewrite them to
    # the final install prefix inside the image.
    def swap(value: str) -> str:
        return value.replace(host_prefix, image_prefix)

    return EnvDiff(
        assignments={k: swap(v) for k, v in diff.assignments.items()},
        path_diffs={
            k: PathListDiff(
                prepend=tuple(swap(p) for p in d.prepend),
                append=tuple(swap(p) for p in d.append),
            )
            for k, d in diff.path_diffs.items()
        },
    )


def _build_smoke_test_env(sdk_home: Path, env_diff: EnvDiff) -> dict[str, str]:
    child_env = {key: value for key, value in os.environ.items() if key not in _PATH_LIKE_KEYS}
    child_env["HOME"] = _BASELINE_HOME
    child_env["PATH"] = _BASELINE_PATH

    overlay: dict[str, str] = dict(env_diff.assignments)
    for key, diff in env_diff.path_diffs.items():
        base = child_env.get(key, "")
        parts: list[str] = []
        if diff.prepend:
            parts.append(":".join(diff.prepend))
        if base:
            parts.append(base)
        if diff.append:
            parts.append(":".join(diff.append))
        overlay[key] = ":".join(p for p in parts if p)

    child_env.update(overlay)
    child_env["CANGJIE_HOME"] = str(sdk_home)
    return child_env


def _smoke_test(sdk_home: Path, env_diff: EnvDiff) -> None:
    child_env = _build_smoke_test_env(sdk_home, env_diff)
    for binary in ("cjc", "cjpm"):
        subprocess.run([binary, "--version"], env=child_env, check=True)


@dataclass(frozen=True, slots=True)
class CapturedSdk:
    env_diff: EnvDiff
    sha256: str


def capture_sdk(
    *,
    archive_url: str,
    archive_sha256: str,
    workdir: Path,
    install_prefix: str = "/opt",
    run_smoke_test: bool = True,
) -> CapturedSdk:
    """Download + extract one SDK archive, capture its envsetup diff.

    ``workdir`` is caller-managed (typically a ``tempfile.TemporaryDirectory``).
    Returns the image-relative EnvDiff plus the verified sha256.
    """
    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    archive_path = workdir / "sdk.tar.gz"
    download_archive(archive_url, archive_path)
    if archive_sha256:
        verify_sha256(archive_path, archive_sha256)
    computed_sha = compute_sha256(archive_path)

    sdk_root_on_host = workdir / "sdk-root"
    install = Path(install_prefix)
    sdk_tree_parent = sdk_root_on_host / install.relative_to("/")
    sdk_tree_parent.mkdir(parents=True, exist_ok=True)
    extract_archive(archive_path, sdk_tree_parent)
    archive_path.unlink()

    sdk_home_on_host = sdk_tree_parent / "cangjie"
    raw_diff = capture_envsetup(sdk_home_on_host)
    if run_smoke_test:
        _smoke_test(sdk_home_on_host, raw_diff)
    sdk_home_in_image = str(install / "cangjie")
    env_diff = rewrite_paths(raw_diff, str(sdk_home_on_host), sdk_home_in_image)

    return CapturedSdk(env_diff=env_diff, sha256=computed_sha)


@dataclass(frozen=True, slots=True)
class CapturedArch:
    """SDK source + arch-specific envsetup diff, ready to bake into a Dockerfile."""

    source: ArchSource
    env_diff: EnvDiff


def _capture_one(
    arch: ArchVariant, artifact: PlatformArtifact, run_smoke_test: bool
) -> CapturedArch:
    with tempfile.TemporaryDirectory(prefix="cangjie-capture-") as tmp:
        result = capture_sdk(
            archive_url=artifact.url,
            archive_sha256=artifact.sha256,
            workdir=Path(tmp),
            run_smoke_test=run_smoke_test and arch.name == "amd64",
        )
    return CapturedArch(
        source=ArchSource(arch=arch.name, url=artifact.url, sha256=result.sha256),
        env_diff=result.env_diff,
    )


def capture_sources(
    platforms: Mapping[str, PlatformArtifact],
    *,
    run_smoke_test: bool = True,
) -> list[CapturedArch]:
    """Fetch one SDK per available architecture and capture each arch's envsetup.

    Arches run in parallel — each is dominated by network + tar I/O (releases
    the GIL), so threading the few seconds of bash/subprocess work is safe.
    Each arch's env diff is kept independent because envsetup paths embed the
    arch's native lib dir (``linux_x86_64_cjnative`` vs
    ``linux_aarch64_cjnative``). Smoke test only runs on the host-matching arch.
    """
    jobs = [
        (arch, platforms[arch.manifest_key])
        for arch in ARCH_VARIANTS
        if arch.manifest_key in platforms
    ]
    if not jobs:
        return []

    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = [
            executor.submit(_capture_one, arch, artifact, run_smoke_test) for arch, artifact in jobs
        ]
        return [f.result() for f in futures]
