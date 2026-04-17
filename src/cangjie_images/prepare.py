from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path

from cangjie_images.http_client import http_client, stream_download

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
# Vars treated as ':'-separated path lists. For these we emit a Dockerfile
# ENV that preserves the base image's existing value via $KEY expansion
# instead of clobbering it with whatever the runner happens to have.
_PATH_LIKE_KEYS: frozenset[str] = frozenset(
    {"PATH", "LD_LIBRARY_PATH", "PKG_CONFIG_PATH", "CPATH", "LIBRARY_PATH", "MANPATH"}
)


@dataclass(frozen=True, slots=True)
class PathListDiff:
    """Prefix and suffix entries added around a base value of a :-separated list."""

    prepend: tuple[str, ...]
    append: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not self.prepend and not self.append


@dataclass(frozen=True, slots=True)
class EnvDiff:
    """Structured diff between baseline and envsetup-applied environments."""

    # Scalar KEY=VALUE assignments (new vars or non-list vars with a changed value).
    assignments: dict[str, str]
    # Path-list vars that existed in the baseline: expressed as $KEY-preserving prepend/append.
    path_diffs: dict[str, PathListDiff]

    def as_dict(self) -> dict[str, str]:
        """Flatten back to KEY=VALUE form (for smoke tests and backwards compat)."""
        out = dict(self.assignments)
        for key, diff in self.path_diffs.items():
            parts: list[str] = []
            if diff.prepend:
                parts.append(":".join(diff.prepend))
            parts.append(f"${key}")
            if diff.append:
                parts.append(":".join(diff.append))
            out[key] = ":".join(parts)
        return out


@dataclass(frozen=True, slots=True)
class PreparedBuild:
    context_dir: Path
    dockerfile: Path
    sdk_dir: Path
    env_diff: EnvDiff


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


def download_archive(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with http_client(timeout=None) as client, dest.open("wb") as handle:
        stream_download(client, url, handle)


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
        return PathListDiff(prepend=new_entries, append=())

    old_len = len(old_entries)
    for i in range(len(new_entries) - old_len + 1):
        if new_entries[i : i + old_len] == old_entries:
            return PathListDiff(
                prepend=new_entries[:i],
                append=new_entries[i + old_len :],
            )

    # envsetup removed or reordered baseline entries. Keep only the
    # genuinely new ones as a prepend so we don't drop user-set baseline.
    added = tuple(p for p in new_entries if p not in old_entries)
    return PathListDiff(prepend=added, append=())


def capture_envsetup(sdk_home_on_host: Path) -> EnvDiff:
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
            # envsetup introduced a path list that had no baseline; emit as
            # a plain value (colons stripped of empty trailing entries).
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


def _quote_env_value(value: str) -> str:
    # Escape backslash and double-quote; do NOT escape $ because we want
    # $KEY references (for path-list vars) to expand against the base
    # image's inherited env at Dockerfile parse time.
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _format_scalar_env(key: str, value: str) -> str:
    escaped = _quote_env_value(value).replace("$", "\\$")
    return f'ENV {key}="{escaped}"'


def _format_path_env(key: str, diff: PathListDiff) -> str:
    parts: list[str] = []
    if diff.prepend:
        parts.append(":".join(diff.prepend))
    parts.append(f"${key}")
    if diff.append:
        parts.append(":".join(diff.append))
    value = ":".join(parts)
    return f'ENV {key}="{_quote_env_value(value)}"'


def render_dockerfile(
    *,
    base_image: str,
    base_family: str,
    channel: str,
    version: str,
    env_diff: EnvDiff,
    sdk_context_dir: str,
) -> str:
    env_lines: list[str] = []
    for key, value in sorted(env_diff.assignments.items()):
        env_lines.append(_format_scalar_env(key, value))
    for key, diff in sorted(env_diff.path_diffs.items()):
        env_lines.append(_format_path_env(key, diff))
    env_block = "\n".join(env_lines)

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


def _smoke_test(sdk_home: Path, env_diff: EnvDiff) -> None:
    # Reconstruct concrete values by expanding $KEY against the current env,
    # then overlay onto os.environ so the smoke test runs with the same
    # resolution rules as the eventual container.
    overlay: dict[str, str] = dict(env_diff.assignments)
    for key, diff in env_diff.path_diffs.items():
        base = os.environ.get(key, "")
        parts: list[str] = []
        if diff.prepend:
            parts.append(":".join(diff.prepend))
        if base:
            parts.append(base)
        if diff.append:
            parts.append(":".join(diff.append))
        overlay[key] = ":".join(p for p in parts if p)

    child_env = {**os.environ, **overlay, "CANGJIE_HOME": str(sdk_home)}
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
    raw_diff = capture_envsetup(sdk_home_on_host)
    _smoke_test(sdk_home_on_host, raw_diff)
    env_diff = rewrite_paths(raw_diff, str(sdk_home_on_host), sdk_home_in_image)

    dockerfile = output_dir / "Dockerfile"
    dockerfile.write_text(
        render_dockerfile(
            base_image=base_image,
            base_family=base_family,
            channel=channel,
            version=version,
            env_diff=env_diff,
            sdk_context_dir="sdk-root",
        ),
        encoding="utf-8",
    )

    return PreparedBuild(
        context_dir=output_dir,
        dockerfile=dockerfile,
        sdk_dir=sdk_home_on_host,
        env_diff=env_diff,
    )
