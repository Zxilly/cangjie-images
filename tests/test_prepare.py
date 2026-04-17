from __future__ import annotations

from cangjie_images.prepare import (
    EnvDiff,
    PathListDiff,
    _should_exclude,
    _split_path_diff,
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


def test_split_path_diff_finds_baseline_in_middle() -> None:
    before = "/usr/bin:/bin"
    after = "/opt/cangjie/bin:/opt/cangjie/tools/bin:/usr/bin:/bin:/root/.cjpm/bin"
    diff = _split_path_diff(before, after)
    assert diff.prepend == ("/opt/cangjie/bin", "/opt/cangjie/tools/bin")
    assert diff.append == ("/root/.cjpm/bin",)


def test_split_path_diff_baseline_only_prepended() -> None:
    diff = _split_path_diff("/usr/bin", "/opt/cj/bin:/usr/bin")
    assert diff.prepend == ("/opt/cj/bin",)
    assert diff.append == ()


def test_split_path_diff_empty_baseline_treats_all_as_prepend() -> None:
    diff = _split_path_diff("", "/opt/cj/runtime/lib:/opt/cj/tools/lib")
    assert diff.prepend == ("/opt/cj/runtime/lib", "/opt/cj/tools/lib")
    assert diff.append == ()


def test_split_path_diff_trailing_colon_is_stripped() -> None:
    # envsetup.sh on 1.0.5 emits LD_LIBRARY_PATH=...:$LD_LIBRARY_PATH where
    # the trailing expansion is empty, leaving a dangling colon.
    diff = _split_path_diff("", "/opt/cj/lib:")
    assert diff.prepend == ("/opt/cj/lib",)
    assert diff.append == ()


def test_split_path_diff_dedupes_prepend_entries() -> None:
    # If envsetup ends up emitting duplicate entries (e.g. double-source),
    # dedupe so the rendered ENV line stays tight.
    before = "/usr/bin"
    after = "/opt/cj/bin:/opt/cj/bin:/usr/bin"
    diff = _split_path_diff(before, after)
    assert diff.prepend == ("/opt/cj/bin",)


def test_split_path_diff_falls_back_when_baseline_not_contiguous() -> None:
    before = "/a:/b"
    after = "/a:/c"  # /b dropped, /c added — no contiguous match
    diff = _split_path_diff(before, after)
    assert diff.prepend == ("/c",)
    assert diff.append == ()


def test_rewrite_paths_replaces_host_prefix() -> None:
    env = EnvDiff(
        assignments={"CANGJIE_HOME": "/tmp/stage/opt/cangjie"},
        path_diffs={
            "PATH": PathListDiff(
                prepend=("/tmp/stage/opt/cangjie/bin", "/tmp/stage/opt/cangjie/tools/bin"),
                append=("/root/.cjpm/bin",),
            ),
            "LD_LIBRARY_PATH": PathListDiff(
                prepend=("/tmp/stage/opt/cangjie/runtime/lib/linux_x86_64_cjnative",),
                append=(),
            ),
        },
    )
    result = rewrite_paths(env, "/tmp/stage/opt/cangjie", "/opt/cangjie")
    assert result.assignments["CANGJIE_HOME"] == "/opt/cangjie"
    assert result.path_diffs["PATH"].prepend == ("/opt/cangjie/bin", "/opt/cangjie/tools/bin")
    assert result.path_diffs["PATH"].append == ("/root/.cjpm/bin",)
    assert result.path_diffs["LD_LIBRARY_PATH"].prepend == (
        "/opt/cangjie/runtime/lib/linux_x86_64_cjnative",
    )


def test_render_dockerfile_path_uses_env_expansion() -> None:
    diff = EnvDiff(
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
    content = render_dockerfile(
        base_image="debian:bookworm-slim",
        base_family="debian",
        channel="lts",
        version="1.0.5",
        env_diff=diff,
        sdk_context_dir="sdk-root",
    )
    assert 'ENV CANGJIE_HOME="/opt/cangjie"' in content
    assert 'ENV PATH="/opt/cangjie/bin:/opt/cangjie/tools/bin:$PATH:/root/.cjpm/bin"' in content
    assert 'ENV LD_LIBRARY_PATH="/opt/cangjie/runtime/lib/linux_x86_64_cjnative:$LD_LIBRARY_PATH"' in content


def test_render_dockerfile_scalar_env_escapes_dollar() -> None:
    diff = EnvDiff(
        assignments={"X": 'a"b$c\\d'},
        path_diffs={},
    )
    content = render_dockerfile(
        base_image="x",
        base_family="debian",
        channel="c",
        version="v",
        env_diff=diff,
        sdk_context_dir="sdk-root",
    )
    # Scalars escape $ so values are treated as literal strings.
    assert 'ENV X="a\\"b\\$c\\\\d"' in content
