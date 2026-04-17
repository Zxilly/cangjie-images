from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tarfile
import textwrap
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from cangjie_images.config import USER_AGENT

EXCLUDE_PREFIXES: tuple[str, ...] = (
    "cangjie/lib/windows_",
    "cangjie/runtime/lib/windows_",
    "cangjie/modules/windows_",
    "cangjie/third_party/mingw",
)
EXCLUDE_SUFFIXES: tuple[str, ...] = (".dll", ".dll.a")

_BASELINE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_BASELINE_HOME = "/root"
_VOLATILE_ENV_KEYS: frozenset[str] = frozenset({"PWD", "OLDPWD", "SHLVL", "_", "HOME"})


@dataclass(frozen=True, slots=True)
class PreparedBuild:
    context_dir: Path
    dockerfile: Path
    sdk_dir: Path
    env_vars: dict[str, str]


def _should_exclude(name: str) -> bool:
    if any(part in EXCLUDE_PREFIXES for part in ()):
        return False
    # Normalise leading "./" that some tars produce.
    normalised = name.lstrip("./")
    for prefix in EXCLUDE_PREFIXES:
        if normalised == prefix.rstrip("/") or normalised.startswith(prefix):
            return True
    for suffix in EXCLUDE_SUFFIXES:
        # Only exclude dll artefacts that sit directly under cangjie/lib/.
        if normalised.startswith("cangjie/lib/") and normalised.endswith(suffix):
            stem = normalised[len("cangjie/lib/") :]
            if "/" not in stem:
                return True
    return False


def download_archive(url: str, dest: Path, *, chunk_size: int = 1024 * 1024) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=300) as response, dest.open("wb") as handle:
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            handle.write(chunk)


def verify_sha256(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual.lower() != expected.lower():
        raise RuntimeError(f"sha256 mismatch for {path}: expected {expected}, got {actual}")


def extract_archive(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            if _should_exclude(member.name):
                continue
            tar.extract(member, dest, filter="data")


def capture_envsetup(sdk_home_on_host: Path) -> dict[str, str]:
    envsetup = sdk_home_on_host / "envsetup.sh"
    if not envsetup.is_file():
        raise FileNotFoundError(f"envsetup.sh not found under {sdk_home_on_host}")

    clean_env = {"HOME": _BASELINE_HOME, "PATH": _BASELINE_PATH}

    def _run(script: str) -> dict[str, str]:
        result = subprocess.run(
            ["bash", "--norc", "--noprofile", "-c", script],
            env=clean_env,
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
    after = _run(f'. "{envsetup}" >/dev/null 2>&1; env -0')

    diff: dict[str, str] = {}
    for key, value in sorted(after.items()):
        if key in _VOLATILE_ENV_KEYS:
            continue
        if before.get(key) == value:
            continue
        diff[key] = value
    return diff


def rewrite_paths(env_vars: dict[str, str], host_prefix: str, image_prefix: str) -> dict[str, str]:
    # envsetup.sh resolves CANGJIE_HOME via readlink of its own location,
    # so captured paths point at the host staging dir. Rewrite them to
    # the final install prefix inside the image.
    return {key: value.replace(host_prefix, image_prefix) for key, value in env_vars.items()}


def _format_env_line(key: str, value: str) -> str:
    quoted = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")
    return f'ENV {key}="{quoted}"'


def render_dockerfile(
    *,
    base_image: str,
    base_family: str,
    channel: str,
    version: str,
    env_vars: dict[str, str],
    sdk_context_dir: str,
) -> str:
    env_block = "\n".join(_format_env_line(k, v) for k, v in sorted(env_vars.items()))
    lines = [
        "# syntax=docker/dockerfile:1.7",
        "",
        f"FROM --platform=$TARGETPLATFORM {base_image}",
        "",
        "RUN --mount=type=bind,source=scripts/install-base-deps.sh,target=/usr/local/bin/install-base-deps \\",
        f"    install-base-deps {base_family}",
        "",
        f"COPY --link {sdk_context_dir}/ /",
        "",
        env_block,
        "",
        'LABEL org.opencontainers.image.title="Cangjie"',
        'LABEL org.opencontainers.image.description="Prebuilt Cangjie SDK image"',
        f'LABEL io.cangjie.channel="{channel}"',
        f'LABEL io.cangjie.version="{version}"',
        "",
        "WORKDIR /workspace",
        'CMD ["bash"]',
        "",
    ]
    return "\n".join(lines)


def _smoke_test(sdk_home: Path, env_vars: dict[str, str]) -> None:
    child_env = {**os.environ, **env_vars, "CANGJIE_HOME": str(sdk_home)}
    for binary in ("cjc", "cjpm"):
        subprocess.run([binary, "--version"], env=child_env, check=True)


def prepare_build_context(
    *,
    archive_url: str,
    archive_sha256: str,
    base_image: str,
    base_family: str,
    channel: str,
    version: str,
    output_dir: Path,
    scripts_dir: Path,
    sdk_install_prefix: str = "/opt",
) -> PreparedBuild:
    output_dir = output_dir.resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # Scripts still used by the Dockerfile (bind-mounted, never in the image).
    target_scripts = output_dir / "scripts"
    target_scripts.mkdir()
    shutil.copy2(scripts_dir / "install-base-deps.sh", target_scripts / "install-base-deps.sh")

    archive_path = output_dir / "sdk.tar.gz"
    download_archive(archive_url, archive_path)
    if archive_sha256:
        verify_sha256(archive_path, archive_sha256)

    sdk_root_on_host = output_dir / "sdk-root"
    install_prefix = Path(sdk_install_prefix)
    sdk_tree_parent = sdk_root_on_host / install_prefix.relative_to("/")
    sdk_tree_parent.mkdir(parents=True)
    extract_archive(archive_path, sdk_tree_parent)
    archive_path.unlink()

    sdk_home_on_host = sdk_tree_parent / "cangjie"
    sdk_home_in_image = str(install_prefix / "cangjie")
    raw_env = capture_envsetup(sdk_home_on_host)
    _smoke_test(sdk_home_on_host, raw_env)
    env_vars = rewrite_paths(raw_env, str(sdk_home_on_host), sdk_home_in_image)

    dockerfile = output_dir / "Dockerfile"
    dockerfile.write_text(
        render_dockerfile(
            base_image=base_image,
            base_family=base_family,
            channel=channel,
            version=version,
            env_vars=env_vars,
            sdk_context_dir="sdk-root",
        ),
        encoding="utf-8",
    )

    return PreparedBuild(
        context_dir=output_dir,
        dockerfile=dockerfile,
        sdk_dir=sdk_home_on_host,
        env_vars=env_vars,
    )
