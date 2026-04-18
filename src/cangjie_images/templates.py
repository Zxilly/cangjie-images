from __future__ import annotations

from importlib import resources
from typing import TYPE_CHECKING, get_args

from cangjie_images.config import ARCH_VARIANTS, Arch, BaseFamily, Channel
from cangjie_images.prepare import ArchSource

if TYPE_CHECKING:
    from jinja2 import Template

__all__ = ["ArchSource", "render_dockerfile"]

_EXTRACTOR_IMAGE = "debian:bookworm-slim"
_REPO_URL = "https://github.com/Zxilly/cangjie-images"
_DOCS_URL = "https://github.com/Zxilly/cangjie-images#readme"

_DEBIAN_PACKAGES: tuple[str, ...] = (
    "bash",
    "binutils",
    "ca-certificates",
    "curl",
    "findutils",
    "g++",
    "gcc",
    "git",
    "libc6-dev",
    "libssl-dev",
    "make",
    "openssl",
    "pkg-config",
    "procps",
    "tar",
    "unzip",
    "xz-utils",
    "zip",
)

_OPENEULER_PACKAGES: tuple[str, ...] = (
    "bash",
    "binutils",
    "ca-certificates",
    "curl",
    "findutils",
    "gcc",
    "gcc-c++",
    "git",
    "glibc-devel",
    "make",
    "openssl",
    "openssl-devel",
    "pkgconfig",
    "procps-ng",
    "tar",
    "unzip",
    "xz",
    "zip",
)

_TAR_EXCLUDES: tuple[str, ...] = (
    "cangjie/lib/windows_*",
    "cangjie/runtime/lib/windows_*",
    "cangjie/modules/windows_*",
    "cangjie/third_party/mingw",
    "cangjie/lib/*.dll",
    "cangjie/lib/*.dll.a",
)

_SUPPORTED_FAMILIES: frozenset[str] = frozenset(get_args(BaseFamily))
_NATIVE_LIB_TOKEN_BY_ARCH: dict[Arch, str] = {a.name: a.native_lib_token for a in ARCH_VARIANTS}

# Pre-joined line continuations keep the Jinja template free of loop.last
# bookkeeping — the template just interpolates a ready-to-emit block.
_LINE_CONT = " \\\n      "
_TAR_EXCLUDES_BLOCK = _LINE_CONT.join(f"--exclude='{p}'" for p in _TAR_EXCLUDES)
_DEBIAN_PACKAGES_BLOCK = _LINE_CONT.join(_DEBIAN_PACKAGES)
_OPENEULER_PACKAGES_BLOCK = _LINE_CONT.join(_OPENEULER_PACKAGES)

_template: Template | None = None


def _get_template() -> Template:
    """Lazy-load the Jinja template so CLI commands that never render
    (write-digest, merge) don't pay the jinja2 import + file-read cost."""
    global _template
    if _template is None:
        from jinja2 import Environment, StrictUndefined

        env = Environment(
            keep_trailing_newline=True,
            undefined=StrictUndefined,
            autoescape=False,
        )
        _template = env.from_string(
            resources.files("cangjie_images").joinpath("dockerfile.j2").read_text(encoding="utf-8")
        )
    return _template


def render_dockerfile(
    *,
    base_name: str,
    base_image: str,
    base_family: BaseFamily,
    channel: Channel,
    version: str,
    arch: Arch,
    source: ArchSource,
) -> str:
    """Render a fully self-contained single-arch Dockerfile via Jinja2."""
    if source.arch != arch:
        raise ValueError(f"source arch mismatch: expected {arch}, got {source.arch}")
    if not source.sha256:
        raise ValueError(f"sha256 required for arch {arch}")
    if not source.backend:
        raise ValueError(f"backend required for arch {arch}")
    if base_family not in _SUPPORTED_FAMILIES:
        raise ValueError(f"unsupported base family: {base_family}")

    return _get_template().render(
        channel=channel,
        version=version,
        arch=arch,
        base_name=base_name,
        base_image=base_image,
        base_family=base_family,
        source=source,
        native_lib_token=_NATIVE_LIB_TOKEN_BY_ARCH[arch],
        debian_packages_block=_DEBIAN_PACKAGES_BLOCK,
        openeuler_packages_block=_OPENEULER_PACKAGES_BLOCK,
        tar_excludes_block=_TAR_EXCLUDES_BLOCK,
        extractor_image=_EXTRACTOR_IMAGE,
        repo_url=_REPO_URL,
        docs_url=_DOCS_URL,
    )
