from __future__ import annotations

import pytest

from cangjie_images.templates import ArchSource, render_dockerfile


def _source(arch: str = "amd64", backend: str = "cjnative") -> ArchSource:
    return ArchSource(
        arch=arch,  # type: ignore[arg-type]
        url=f"https://example.com/{arch}.tgz",
        sha256="a" * 64,
        backend=backend,
    )


def test_render_dockerfile_single_arch_is_linear() -> None:
    content = render_dockerfile(
        base_name="slim-bookworm",
        base_image="debian:bookworm-slim",
        base_family="debian",
        channel="lts",
        version="1.0.5",
        arch="amd64",
        source=_source(),
        slim=True,
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
    assert (
        "ENV LD_LIBRARY_PATH="
        '"/opt/cangjie/runtime/lib/linux_x86_64_cjnative:/opt/cangjie/tools/lib"' in content
    )
    assert 'ENV PATH="/opt/cangjie/bin:/opt/cangjie/tools/bin:$PATH:/root/.cjpm/bin"' in content
    assert 'LABEL io.cangjie.arch="amd64"' in content


def test_render_dockerfile_arm64_uses_aarch64_token() -> None:
    content = render_dockerfile(
        base_name="bookworm",
        base_image="debian:bookworm-slim",
        base_family="debian",
        channel="lts",
        version="1.0.5",
        arch="arm64",
        source=_source(arch="arm64"),
    )
    assert "linux_aarch64_cjnative" in content
    assert "linux_x86_64" not in content


def test_render_dockerfile_llvm_backend_is_emitted() -> None:
    content = render_dockerfile(
        base_name="bookworm",
        base_image="debian:bookworm-slim",
        base_family="debian",
        channel="lts",
        version="1.0.0",
        arch="amd64",
        source=_source(backend="llvm"),
    )
    assert "linux_x86_64_llvm" in content
    assert "cjnative" not in content
    assert 'LABEL io.cangjie.backend="llvm"' in content


def test_render_dockerfile_emits_oci_metadata_labels() -> None:
    content = render_dockerfile(
        base_name="openeuler-24.03",
        base_image="openeuler/openeuler:24.03-lts-sp2",
        base_family="openeuler",
        channel="lts",
        version="1.0.5",
        arch="amd64",
        source=_source(),
    )
    assert 'LABEL org.opencontainers.image.title="Cangjie 1.0.5 (openeuler-24.03/amd64)"' in content
    assert 'LABEL org.opencontainers.image.version="1.0.5"' in content
    assert (
        'LABEL org.opencontainers.image.source="https://github.com/Zxilly/cangjie-images"'
        in content
    )
    assert 'LABEL org.opencontainers.image.licenses="MIT"' in content
    assert 'LABEL org.opencontainers.image.base.name="openeuler/openeuler:24.03-lts-sp2"' in content
    assert 'LABEL io.cangjie.base="openeuler-24.03"' in content
    assert 'LABEL io.cangjie.base.family="openeuler"' in content
    assert 'LABEL io.cangjie.backend="cjnative"' in content
    assert 'LABEL io.cangjie.sdk.url="https://example.com/amd64.tgz"' in content
    assert f'LABEL io.cangjie.sdk.sha256="{"a" * 64}"' in content


def test_render_dockerfile_openeuler_uses_dnf() -> None:
    content = render_dockerfile(
        base_name="openeuler-24.03",
        base_image="openeuler/openeuler:24.03-lts-sp1",
        base_family="openeuler",
        channel="lts",
        version="1.0.5",
        arch="amd64",
        source=_source(),
    )
    assert "dnf install -y" in content
    assert "gcc-c++" in content
    assert "apt-get" not in content


def _extract_install_block(content: str, marker: str) -> str:
    """Return the substring between the package-manager install line and the
    next blank line, so assertions can check the exact install list without
    matching unrelated tokens elsewhere in the Dockerfile (labels, URLs, etc.)."""
    start = content.index(marker)
    end = content.index("\nEOF", start)
    return content[start:end]


def test_render_dockerfile_debian_slim_drops_dev_toolchain() -> None:
    content = render_dockerfile(
        base_name="slim-bookworm",
        base_image="debian:bookworm-slim",
        base_family="debian",
        channel="lts",
        version="1.0.5",
        arch="amd64",
        source=_source(),
        slim=True,
    )
    install = _extract_install_block(content, "apt-get install")
    for pkg in ("ca-certificates", "gcc", "libc6-dev", "libssl3"):
        assert pkg in install
    for pkg in ("g++", "git", "make", "pkg-config", "libssl-dev", "unzip", "xz-utils"):
        assert pkg not in install, f"slim variant must not install {pkg!r}"
    assert 'LABEL io.cangjie.slim="true"' in content


def test_render_dockerfile_openeuler_slim_uses_minimal_deps() -> None:
    content = render_dockerfile(
        base_name="slim-openeuler-24.03",
        base_image="openeuler/openeuler:24.03-lts-sp2",
        base_family="openeuler",
        channel="lts",
        version="1.0.5",
        arch="amd64",
        source=_source(),
        slim=True,
    )
    install = _extract_install_block(content, "dnf install")
    for pkg in ("ca-certificates", "gcc", "glibc-devel", "openssl-libs"):
        assert pkg in install
    for pkg in ("gcc-c++", "git", "make", "pkgconfig", "openssl-devel", "unzip"):
        assert pkg not in install, f"openeuler slim must not install {pkg!r}"
    assert 'LABEL io.cangjie.slim="true"' in content


def test_render_dockerfile_debian_full_uses_buildpack_deps() -> None:
    content = render_dockerfile(
        base_name="bookworm",
        base_image="buildpack-deps:bookworm",
        base_family="debian",
        channel="lts",
        version="1.0.5",
        arch="amd64",
        source=_source(),
    )
    assert 'LABEL io.cangjie.slim="false"' in content
    assert "FROM buildpack-deps:bookworm" in content
    # buildpack-deps already ships the dev toolchain, so the template must
    # not emit an apt-get install step on top.
    assert "apt-get install" not in content
    assert "apt-get update" not in content
    assert 'LABEL org.opencontainers.image.base.name="buildpack-deps:bookworm"' in content


def test_render_dockerfile_rejects_arch_mismatch() -> None:
    with pytest.raises(ValueError, match="source arch mismatch"):
        render_dockerfile(
            base_name="bookworm",
            base_image="debian:bookworm-slim",
            base_family="debian",
            channel="lts",
            version="1.0.5",
            arch="arm64",
            source=_source(arch="amd64"),
        )


def test_render_dockerfile_rejects_missing_sha256() -> None:
    with pytest.raises(ValueError, match="sha256 required"):
        render_dockerfile(
            base_name="bookworm",
            base_image="debian:bookworm-slim",
            base_family="debian",
            channel="lts",
            version="1.0.5",
            arch="amd64",
            source=ArchSource(arch="amd64", url="u", sha256="", backend="cjnative"),
        )


def test_render_dockerfile_rejects_missing_backend() -> None:
    with pytest.raises(ValueError, match="backend required"):
        render_dockerfile(
            base_name="bookworm",
            base_image="debian:bookworm-slim",
            base_family="debian",
            channel="lts",
            version="1.0.5",
            arch="amd64",
            source=ArchSource(arch="amd64", url="u", sha256="a" * 64, backend=""),
        )


def test_render_dockerfile_rejects_unsupported_family() -> None:
    with pytest.raises(ValueError, match="unsupported base family"):
        render_dockerfile(
            base_name="bookworm",
            base_image="x",
            base_family="alpine",  # type: ignore[arg-type]
            channel="lts",
            version="1.0.5",
            arch="amd64",
            source=_source(),
        )
