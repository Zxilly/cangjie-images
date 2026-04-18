from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Channel = Literal["lts", "sts", "nightly"]
StableChannel = Literal["lts", "sts"]
BaseFamily = Literal["debian", "openeuler"]
Arch = Literal["amd64", "arm64"]

STABLE_CHANNELS: tuple[StableChannel, ...] = ("lts", "sts")


@dataclass(frozen=True, slots=True)
class BaseVariant:
    name: str
    image: str
    family: BaseFamily
    default: bool = False


@dataclass(frozen=True, slots=True)
class ArchVariant:
    name: Arch
    platform: str
    manifest_key: str
    nightly_arch: str
    runner: str
    native_lib_token: str


DEFAULT_IMAGE_NAME = "zxilly/cangjie"
STABLE_MANIFEST_URL = (
    "https://raw.githubusercontent.com/Zxilly/"
    "cangjie-version-manifest/refs/heads/master/versions.json"
)
NIGHTLY_RELEASE_API_URL = (
    "https://api.gitcode.com/api/v5/repos/Cangjie/nightly_build/releases/latest"
)
NIGHTLY_TOKEN_ENV = "CANGJIE_NIGHTLY_API_KEY"
DOCKER_HUB_PAGE_SIZE = 100
USER_AGENT = "cangjie-images/0.1.0"

BASE_VARIANTS: tuple[BaseVariant, ...] = (
    BaseVariant("bookworm", "debian:bookworm", "debian", default=True),
    BaseVariant("slim-bookworm", "debian:bookworm-slim", "debian"),
    BaseVariant("bullseye", "debian:bullseye", "debian"),
    BaseVariant("slim-bullseye", "debian:bullseye-slim", "debian"),
    BaseVariant("trixie", "debian:trixie", "debian"),
    BaseVariant("slim-trixie", "debian:trixie-slim", "debian"),
    BaseVariant("openeuler-24.03", "openeuler/openeuler:24.03-lts-sp2", "openeuler"),
    BaseVariant("openeuler-22.03", "openeuler/openeuler:22.03-lts-sp4", "openeuler"),
    BaseVariant("openeuler-20.03", "openeuler/openeuler:20.03-lts-sp4", "openeuler"),
)

ARCH_VARIANTS: tuple[ArchVariant, ...] = (
    ArchVariant(
        name="amd64",
        platform="linux/amd64",
        manifest_key="linux-x64",
        nightly_arch="x64",
        runner="ubuntu-24.04",
        native_lib_token="linux_x86_64",
    ),
    ArchVariant(
        name="arm64",
        platform="linux/arm64",
        manifest_key="linux-arm64",
        nightly_arch="aarch64",
        runner="ubuntu-24.04-arm",
        native_lib_token="linux_aarch64",
    ),
)
