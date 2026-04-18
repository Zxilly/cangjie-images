from __future__ import annotations

import pytest

from cangjie_images.prepare import EnvDiff, PathListDiff
from cangjie_images.templates import ArchSource, render_dockerfile


def _sample_env() -> EnvDiff:
    return EnvDiff(
        assignments={"CANGJIE_HOME": "/opt/cangjie"},
        path_diffs={
            "PATH": PathListDiff(
                prepend=("/opt/cangjie/bin", "/opt/cangjie/tools/bin"),
                append=("/root/.cjpm/bin",),
            ),
            "LD_LIBRARY_PATH": PathListDiff(
                prepend=("/opt/cangjie/runtime/lib/linux_x86_64_cjnative",),
                append=(),
            ),
        },
    )


def _amd64_source() -> ArchSource:
    return ArchSource(arch="amd64", url="https://example.com/amd64.tgz", sha256="a" * 64)


def test_render_dockerfile_single_arch_is_linear() -> None:
    content = render_dockerfile(
        base_image="debian:bookworm-slim",
        base_family="debian",
        channel="lts",
        version="1.0.5",
        arch="amd64",
        env_diff=_sample_env(),
        source=_amd64_source(),
    )

    assert "# syntax=docker/dockerfile:1.7" in content
    assert "ARG TARGETARCH" not in content
    assert "FROM sdk-${TARGETARCH}" not in content
    assert "FROM scratch AS sdk" in content
    assert f"ADD --checksum=sha256:{'a' * 64}" in content
    assert "FROM debian:bookworm-slim AS extractor" in content
    assert "--mount=from=sdk,source=/sdk.tar.gz,target=/sdk.tar.gz" in content
    assert "--exclude='cangjie/lib/windows_*'" in content
    assert "apt-get install -y --no-install-recommends" in content
    assert 'ENV CANGJIE_HOME="/opt/cangjie"' in content
    assert 'ENV PATH="/opt/cangjie/bin:/opt/cangjie/tools/bin:$PATH:/root/.cjpm/bin"' in content
    assert 'LABEL io.cangjie.arch="amd64"' in content


def test_render_dockerfile_openeuler_uses_dnf() -> None:
    content = render_dockerfile(
        base_image="openeuler/openeuler:24.03-lts-sp1",
        base_family="openeuler",
        channel="lts",
        version="1.0.5",
        arch="amd64",
        env_diff=_sample_env(),
        source=_amd64_source(),
    )
    assert "dnf install -y" in content
    assert "gcc-c++" in content
    assert "apt-get" not in content


def test_render_dockerfile_scalar_env_escapes_dollar() -> None:
    diff = EnvDiff(assignments={"X": 'a"b$c\\d'}, path_diffs={})
    content = render_dockerfile(
        base_image="debian:bookworm-slim",
        base_family="debian",
        channel="lts",
        version="1.0.5",
        arch="amd64",
        env_diff=diff,
        source=_amd64_source(),
    )
    assert 'ENV X="a\\"b\\$c\\\\d"' in content


def test_render_dockerfile_rejects_arch_mismatch() -> None:
    with pytest.raises(ValueError, match="source arch mismatch"):
        render_dockerfile(
            base_image="debian:bookworm-slim",
            base_family="debian",
            channel="lts",
            version="1.0.5",
            arch="arm64",
            env_diff=_sample_env(),
            source=_amd64_source(),
        )


def test_render_dockerfile_rejects_missing_sha256() -> None:
    with pytest.raises(ValueError, match="sha256 required"):
        render_dockerfile(
            base_image="debian:bookworm-slim",
            base_family="debian",
            channel="lts",
            version="1.0.5",
            arch="amd64",
            env_diff=_sample_env(),
            source=ArchSource(arch="amd64", url="u", sha256=""),
        )


def test_render_dockerfile_rejects_unsupported_family() -> None:
    with pytest.raises(ValueError, match="unsupported base family"):
        render_dockerfile(
            base_image="x",
            base_family="alpine",  # type: ignore[arg-type]
            channel="lts",
            version="1.0.5",
            arch="amd64",
            env_diff=_sample_env(),
            source=_amd64_source(),
        )
