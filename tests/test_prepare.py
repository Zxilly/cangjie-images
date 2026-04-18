from __future__ import annotations

import pytest

from cangjie_images.prepare import detect_backend


def test_detect_backend_reads_runtime_lib_dir(tmp_path) -> None:
    sdk_home = tmp_path / "cangjie"
    (sdk_home / "runtime" / "lib" / "linux_x86_64_cjnative").mkdir(parents=True)
    assert detect_backend(sdk_home, "linux_x86_64") == "cjnative"


def test_detect_backend_handles_llvm(tmp_path) -> None:
    sdk_home = tmp_path / "cangjie"
    (sdk_home / "runtime" / "lib" / "linux_aarch64_llvm").mkdir(parents=True)
    (sdk_home / "runtime" / "lib" / "linux_x86_64_llvm").mkdir(parents=True)
    # Each probe is scoped to one arch's prefix, so sibling arches don't collide.
    assert detect_backend(sdk_home, "linux_aarch64") == "llvm"


def test_detect_backend_raises_when_missing(tmp_path) -> None:
    sdk_home = tmp_path / "cangjie"
    (sdk_home / "runtime" / "lib").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="no linux_x86_64_"):
        detect_backend(sdk_home, "linux_x86_64")


def test_detect_backend_rejects_ambiguous_layout(tmp_path) -> None:
    sdk_home = tmp_path / "cangjie"
    (sdk_home / "runtime" / "lib" / "linux_x86_64_cjnative").mkdir(parents=True)
    (sdk_home / "runtime" / "lib" / "linux_x86_64_llvm").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="multiple backends"):
        detect_backend(sdk_home, "linux_x86_64")


def test_detect_backend_missing_runtime_lib_dir(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        detect_backend(tmp_path / "cangjie", "linux_x86_64")
