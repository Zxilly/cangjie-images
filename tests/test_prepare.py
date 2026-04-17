from __future__ import annotations

from cangjie_images.prepare import (
    _should_exclude,
    render_dockerfile,
    rewrite_paths,
)


def test_should_exclude_windows_runtime() -> None:
    assert _should_exclude("cangjie/runtime/lib/windows_x86_64_cjnative/libfoo.so")
    assert _should_exclude("cangjie/lib/windows_x86_64_cjnative/libbar.a")
    assert _should_exclude("cangjie/modules/windows_x86_64_cjnative/core.cjo")
    assert _should_exclude("cangjie/third_party/mingw/bin/gcc")
    assert _should_exclude("cangjie/third_party/mingw")


def test_should_exclude_top_level_dlls() -> None:
    assert _should_exclude("cangjie/lib/libstdFFI.dll")
    assert _should_exclude("cangjie/lib/libstdFFI.dll.a")


def test_should_keep_linux_artifacts() -> None:
    assert not _should_exclude("cangjie/bin/cjc")
    assert not _should_exclude("cangjie/lib/libstdFFI.so")
    assert not _should_exclude("cangjie/lib/linux_x86_64_cjnative/libboundscheck.so")
    assert not _should_exclude("cangjie/runtime/lib/linux_aarch64_cjnative/libcangjie-runtime.a")
    assert not _should_exclude("cangjie/third_party/llvm/bin/clang")
    assert not _should_exclude("cangjie/envsetup.sh")


def test_rewrite_paths_replaces_host_prefix_with_image_prefix() -> None:
    env = {
        "CANGJIE_HOME": "/tmp/stage/opt/cangjie",
        "PATH": "/tmp/stage/opt/cangjie/bin:/tmp/stage/opt/cangjie/tools/bin:/usr/bin",
        "LD_LIBRARY_PATH": "/tmp/stage/opt/cangjie/runtime/lib/linux_x86_64_cjnative:/tmp/stage/opt/cangjie/tools/lib:",
    }
    result = rewrite_paths(env, "/tmp/stage/opt/cangjie", "/opt/cangjie")
    assert result["CANGJIE_HOME"] == "/opt/cangjie"
    assert result["PATH"] == "/opt/cangjie/bin:/opt/cangjie/tools/bin:/usr/bin"
    assert result["LD_LIBRARY_PATH"] == "/opt/cangjie/runtime/lib/linux_x86_64_cjnative:/opt/cangjie/tools/lib:"


def test_render_dockerfile_contains_expected_directives() -> None:
    content = render_dockerfile(
        base_image="debian:bookworm-slim",
        base_family="debian",
        channel="lts",
        version="1.0.5",
        env_vars={
            "CANGJIE_HOME": "/opt/cangjie",
            "PATH": "/opt/cangjie/bin:/usr/bin",
        },
        sdk_context_dir="sdk-root",
    )
    assert "# syntax=docker/dockerfile:1.7" in content
    assert "FROM --platform=$TARGETPLATFORM debian:bookworm-slim" in content
    assert "install-base-deps debian" in content
    assert "COPY --link sdk-root/ /" in content
    assert 'ENV CANGJIE_HOME="/opt/cangjie"' in content
    assert 'ENV PATH="/opt/cangjie/bin:/usr/bin"' in content
    assert 'LABEL io.cangjie.channel="lts"' in content
    assert 'LABEL io.cangjie.version="1.0.5"' in content


def test_render_dockerfile_escapes_special_characters() -> None:
    content = render_dockerfile(
        base_image="x",
        base_family="debian",
        channel="c",
        version="v",
        env_vars={"X": 'a"b$c\\d'},
        sdk_context_dir="sdk-root",
    )
    assert 'ENV X="a\\"b\\$c\\\\d"' in content
