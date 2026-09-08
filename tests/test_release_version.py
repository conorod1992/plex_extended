"""Tests for release version staging."""

from __future__ import annotations

import importlib.util
import re
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
