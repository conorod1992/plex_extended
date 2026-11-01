"""Tests for release version staging."""

from __future__ import annotations

import importlib.util
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "set_release_version.py"

spec = importlib.util.spec_from_file_location("plex_extended_release_version", SCRIPT)
assert spec is not None and spec.loader is not None
release_version = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = release_version
spec.loader.exec_module(release_version)


def _write_manifest(root: Path, version: str) -> Path:
    path = root / "custom_components" / "plex_extended" / "manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        "{\n"
        '  "domain": "plex_extended",\n'
        f'  "version": "{version}"\n'
        "}\n",
        encoding="utf-8",
    )
    device_path = path.parent / "const.py"
    device_path.write_text(
        f'from typing import Final\nX_PLEX_VERSION: Final = "{version}"\n',
        encoding="utf-8",
    )
    return path


def test_repository_release_version_is_valid() -> None:
    """The committed release metadata should remain internally consistent."""
    version = release_version.current_version()
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version)


def test_set_release_version_updates_manifest(tmp_path: Path) -> None:
    """Staging a release should update the tracked integration version once."""
    manifest = _write_manifest(tmp_path, "0.1.0")

    release_version.set_release_version("0.2.0", tmp_path)

    assert release_version.current_version(tmp_path) == "0.2.0"
    assert '"version": "0.2.0"' in manifest.read_text(encoding="utf-8")
    assert 'X_PLEX_VERSION: Final = "0.2.0"' in (
        manifest.parent / "const.py"
    ).read_text(encoding="utf-8")


def test_set_release_version_rejects_non_semver(tmp_path: Path) -> None:
    """Release versions use the same strict X.Y.Z form as the workflow input."""
    _write_manifest(tmp_path, "0.1.0")

    with pytest.raises(ValueError, match="X.Y.Z"):
        release_version.set_release_version("0.2", tmp_path)


def test_current_version_rejects_ambiguous_manifest(tmp_path: Path) -> None:
    """The helper should fail rather than edit an unexpected manifest shape."""
    path = _write_manifest(tmp_path, "0.1.0")
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '  "version": "0.1.0"',
            '  "version": "0.1.0",\n  "version": "0.1.1"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="exactly one"):
        release_version.current_version(tmp_path)


def test_current_version_rejects_mismatched_device_version(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, "0.1.0")
    (manifest.parent / "const.py").write_text(
        'X_PLEX_VERSION: Final = "0.1.1"\n', encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="inconsistent"):
        release_version.current_version(tmp_path)


def test_release_workflow_stages_every_updated_version_file(tmp_path: Path) -> None:
    """The release commit must include every version change made by the script."""
    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", "-c", "core.autocrlf=false", *args],
            cwd=tmp_path,
            text=True,
        ).strip()

    _write_manifest(tmp_path, "0.1.0")
    git("init", "--quiet")
    git("add", ".")
    baseline_tree = git("write-tree")
    release_version.set_release_version("0.2.0", tmp_path)

    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    commands = [line.strip() for line in workflow.splitlines() if line.strip().startswith("git add ")]
    assert commands
    for command in commands:
        git(*shlex.split(command)[1:])

    staged_paths = set(git("diff", "--cached", "--name-only", baseline_tree).splitlines())
    assert staged_paths == {spec.path for spec in release_version.SPECS}
