"""Tests for per-entry native Assist exposure policy."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"

custom_components = ModuleType("custom_components")
custom_components.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", custom_components)
package = ModuleType("custom_components.plex_extended")
package.__path__ = [str(COMPONENT)]
sys.modules.setdefault("custom_components.plex_extended", package)

def load(name: str):
    full = f"custom_components.plex_extended.{name}"
    spec = importlib.util.spec_from_file_location(full, COMPONENT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module

load("const")
policy = load("llm_policy")

def client(options=None):
    return SimpleNamespace(entry=SimpleNamespace(options=options or {}))

def test_existing_entries_default_to_native_tools_enabled() -> None:
    assert policy.native_llm_tools_enabled(client()) is True

def test_native_tools_can_be_disabled_per_entry() -> None:
    assert policy.native_llm_tools_enabled(client({"enable_llm_tools": False})) is False

def test_enabled_client_filter_preserves_only_opted_in_servers() -> None:
    clients = {
        "Living room": client({"enable_llm_tools": True}),
        "Remote server": client({"enable_llm_tools": False}),
        "Legacy server": client(),
    }
    assert list(policy.enabled_llm_clients(clients)) == ["Living room", "Legacy server"]
