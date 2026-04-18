from __future__ import annotations

import hashlib
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


@dataclass(frozen=True, slots=True)
class ArchSource:
    """SDK archive reference + detected runtime backend for a single architecture."""

    arch: Arch
    url: str
    sha256: str
    backend: str  # "cjnative" or "llvm"


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


def detect_backend(sdk_home: Path, native_lib_token: str) -> str:
    """Infer the runtime backend (cjnative/llvm) by probing ``runtime/lib/``.

    The SDK ships exactly one backend-specific lib dir named
    ``linux_<arch>_<backend>`` (e.g. ``linux_x86_64_cjnative``). Older SDKs
    carry ``llvm``; newer ones carry ``cjnative``. The directory name is the
    ground truth, so we don't need to guess per-version.
    """
    runtime_lib = sdk_home / "runtime" / "lib"
    if not runtime_lib.is_dir():
        raise FileNotFoundError(f"runtime lib dir not found under {sdk_home}")

    prefix = f"{native_lib_token}_"

    candidates = [
        entry.name[len(prefix) :]
        for entry in runtime_lib.iterdir()
        if entry.is_dir() and entry.name.startswith(prefix)
    ]
    if not candidates:
        raise RuntimeError(f"no {prefix}* subdir under {runtime_lib}; cannot determine backend")
    if len(candidates) > 1:
        raise RuntimeError(
            f"multiple backends found under {runtime_lib}: {candidates}; expected one"
        )
    return candidates[0]


def _smoke_test(sdk_home: Path) -> None:
    """Source envsetup.sh in a subshell and run cjc/cjpm --version.

    Only valid on a host whose arch matches the SDK arch, so callers gate it.
    """
    script = (
        f'. "{sdk_home}/envsetup.sh" >/dev/null 2>&1 && '
        "cjc --version >/dev/null && cjpm --version >/dev/null"
    )
    subprocess.run(
        ["bash", "--norc", "--noprofile", "-c", script],
        check=True,
        capture_output=True,
    )


def capture_sdk(
    *,
    archive_url: str,
    archive_sha256: str,
    native_lib_token: str,
    workdir: Path,
    run_smoke_test: bool = True,
) -> tuple[str, str]:
    """Download + extract one SDK archive, return ``(sha256, backend)``.

    ``workdir`` is caller-managed (typically a ``tempfile.TemporaryDirectory``).
    """
    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    archive_path = workdir / "sdk.tar.gz"
    download_archive(archive_url, archive_path)
    if archive_sha256:
        verify_sha256(archive_path, archive_sha256)
    computed_sha = compute_sha256(archive_path)

    sdk_root = workdir / "sdk-root"
    sdk_root.mkdir(parents=True, exist_ok=True)
    extract_archive(archive_path, sdk_root)
    archive_path.unlink()

    sdk_home = sdk_root / "cangjie"
    backend = detect_backend(sdk_home, native_lib_token)
    if run_smoke_test:
        _smoke_test(sdk_home)

    return computed_sha, backend


def _capture_one(arch: ArchVariant, artifact: PlatformArtifact, run_smoke_test: bool) -> ArchSource:
    with tempfile.TemporaryDirectory(prefix="cangjie-capture-") as tmp:
        sha, backend = capture_sdk(
            archive_url=artifact.url,
            archive_sha256=artifact.sha256,
            native_lib_token=arch.native_lib_token,
            workdir=Path(tmp),
            run_smoke_test=run_smoke_test and arch.name == "amd64",
        )
    return ArchSource(arch=arch.name, url=artifact.url, sha256=sha, backend=backend)


def capture_sources(
    platforms: Mapping[str, PlatformArtifact],
    *,
    run_smoke_test: bool = True,
) -> list[ArchSource]:
    """Fetch one SDK per available architecture and probe its runtime backend.

    Arches run in parallel — each is dominated by network + tar I/O. Smoke
    test only runs on the host-matching arch (amd64) since it actually
    executes the binaries.
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
