from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    """Base for models that parse external JSON. Ignores unknown fields."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class PlatformArtifact(_Strict):
    """Download metadata for a single (version, platform) combination."""

    url: str
    sha256: str = ""
    name: str = ""


class ChannelManifest(_Strict):
    """Versions and latest pointer for a single stable channel (lts or sts)."""

    latest: str
    versions: dict[str, dict[str, PlatformArtifact]]


class StableManifest(_Strict):
    """Top-level shape of Zxilly/cangjie-version-manifest's versions.json."""

    channels: dict[str, ChannelManifest]


class DockerHubTag(_Strict):
    name: str
    images: list["DockerHubImage"] = Field(default_factory=list)


class DockerHubImage(_Strict):
    architecture: str = ""
    digest: str = ""
    os: str = ""
    variant: str | None = None


class DockerHubTagPage(_Strict):
    results: list[DockerHubTag] = Field(default_factory=list)
    next: str | None = None


class NightlyAsset(_Strict):
    browser_download_url: str
    name: str


class NightlyRelease(_Strict):
    """Subset of the gitcode release API response we rely on."""

    tag_name: str
    assets: list[NightlyAsset] = Field(default_factory=list)


class DigestMetadata(_Strict):
    release_id: str
    arch: str
    digest: str
