from __future__ import annotations

import tomllib
from pathlib import Path


def test_project_metadata_declares_mit_license() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert project["license"] == {"file": "LICENSE"}
    assert "License :: OSI Approved :: MIT License" in project["classifiers"]

    license_text = Path("LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text


def test_readme_describes_current_layout_and_tag_patterns() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "versions/<channel>/<version>/<base>/<arch>/Dockerfile" in readme
    assert "dockerfiles/" not in readme
    assert "`<version>-slim`" not in readme
    assert "`slim-bookworm`" in readme
    assert "`slim-openeuler-24.03`" in readme
