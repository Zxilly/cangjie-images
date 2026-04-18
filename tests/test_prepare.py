from __future__ import annotations

import cangjie_images.prepare as prepare
from cangjie_images.prepare import (
    EnvDiff,
    PathListDiff,
    _build_smoke_test_env,
    _split_path_diff,
    rewrite_paths,
)


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
    diff = _split_path_diff("", "/opt/cj/lib:")
    assert diff.prepend == ("/opt/cj/lib",)
    assert diff.append == ()


def test_split_path_diff_dedupes_prepend_entries() -> None:
    before = "/usr/bin"
    after = "/opt/cj/bin:/opt/cj/bin:/usr/bin"
    diff = _split_path_diff(before, after)
    assert diff.prepend == ("/opt/cj/bin",)


def test_split_path_diff_falls_back_when_baseline_not_contiguous() -> None:
    before = "/a:/b"
    after = "/a:/c"
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


def test_build_smoke_test_env_uses_clean_baseline(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PATH", "/host/tools:/usr/bin")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/host/lib")
    monkeypatch.setenv("HOME", "/host/home")

    env = _build_smoke_test_env(
        tmp_path / "sdk-root" / "opt" / "cangjie",
        EnvDiff(
            assignments={"LD_LIBRARY_PATH": "/opt/cangjie/runtime/lib", "FOO": "bar"},
            path_diffs={
                "PATH": PathListDiff(
                    prepend=("/opt/cangjie/bin", "/opt/cangjie/tools/bin"),
                    append=("/root/.cjpm/bin",),
                )
            },
        ),
    )

    assert env["PATH"] == (
        f"/opt/cangjie/bin:/opt/cangjie/tools/bin:{prepare._BASELINE_PATH}:/root/.cjpm/bin"
    )
    assert env["LD_LIBRARY_PATH"] == "/opt/cangjie/runtime/lib"
    assert env["HOME"] == prepare._BASELINE_HOME
    assert env["FOO"] == "bar"
    assert "/host/tools" not in env["PATH"]
    assert env["LD_LIBRARY_PATH"] != "/host/lib"
