"""Tests for Plex Extended watched-state mutations."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"


def _install_homeassistant_stubs() -> None:
    homeassistant = ModuleType("homeassistant")
    config_entries = ModuleType("homeassistant.config_entries")
    core = ModuleType("homeassistant.core")

    class ConfigEntry:
        pass

    class HomeAssistant:
        pass

    config_entries.ConfigEntry = ConfigEntry
    core.HomeAssistant = HomeAssistant
    sys.modules.setdefault("homeassistant", homeassistant)
    sys.modules.setdefault("homeassistant.config_entries", config_entries)
    sys.modules.setdefault("homeassistant.core", core)


def _load_component_module(name: str, filename: str) -> ModuleType:
    full_name = f"custom_components.plex_extended.{name}"
    existing = sys.modules.get(full_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(full_name, COMPONENT / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


_install_homeassistant_stubs()
custom_components = sys.modules.setdefault("custom_components", ModuleType("custom_components"))
custom_components.__path__ = [str(ROOT / "custom_components")]
package = sys.modules.setdefault(
    "custom_components.plex_extended", ModuleType("custom_components.plex_extended")
)
package.__path__ = [str(COMPONENT)]

const = _load_component_module("const", "const.py")
client_module = _load_component_module("client", "client.py")
_load_component_module("user_context", "user_context.py")
watch_state = _load_component_module("watch_state", "watch_state.py")

PlexExtendedClient = client_module.PlexExtendedClient
PlexExtendedError = client_module.PlexExtendedError
_set_watch_state = watch_state._set_watch_state


class FakeItem:
    """Minimal Plex item supporting watched-state writes."""

    def __init__(self, rating_key: str, title: str, media_type: str, watched: bool) -> None:
        self.ratingKey = rating_key
        self.title = title
        self.type = media_type
        self._watched = watched
        self.mark_watched_calls = 0
        self.mark_unwatched_calls = 0

    @property
    def isWatched(self) -> bool:
        return self._watched

    @property
    def isPlayed(self) -> bool:
        return self._watched

    def markWatched(self):
        self.mark_watched_calls += 1
        self._watched = True
        return self

    def markUnwatched(self):
        self.mark_unwatched_calls += 1
        self._watched = False
        return self


class IgnoringItem(FakeItem):
    """Plex item whose server never accepts the requested mutation."""

    def markWatched(self):
        self.mark_watched_calls += 1
        return self


class FakeLibrary:
    def sections(self):
        return []


class FakeServer:
    def __init__(self, accounts=None) -> None:
        self.library = FakeLibrary()
        self.accounts = accounts or []
        self.items: dict[str, object] = {}
        self.switched: dict[str, FakeServer] = {}
        self.switch_calls: list[str] = []
        self.fetch_calls: list[str] = []

    def systemAccounts(self):
        return list(self.accounts)

    def switchUser(self, name):
        self.switch_calls.append(str(name))
        return self.switched[str(name)]

    def fetchItem(self, rating_key):
        key = str(rating_key)
        self.fetch_calls.append(key)
        return self.items[key]


def _client(server: FakeServer, default_user_id: str | None = None) -> PlexExtendedClient:
    client = object.__new__(PlexExtendedClient)
    client._server = server
    options = {}
    if default_user_id is not None:
        options[const.CONF_DEFAULT_USER_ID] = default_user_id
    client.entry = SimpleNamespace(options=options)
    return client


def test_mark_watched_changes_leaf_item_and_verifies_server_state() -> None:
    server = FakeServer()
    item = FakeItem("42", "Alien", "movie", False)
    server.items["42"] = item

    result = _set_watch_state(_client(server), {"rating_key": "42"}, watched=True)

    assert item.mark_watched_calls == 1
    assert server.fetch_calls == ["42", "42"]
    assert result == {
        "success": True,
        "operation": "mark_watched",
        "rating_key": "42",
        "type": "movie",
        "title": "Alien",
        "previous_watched": False,
        "watched": True,
        "scope": "item",
    }


def test_mark_unwatched_changes_leaf_item() -> None:
    server = FakeServer()
    item = FakeItem("77", "Pilot", "episode", True)
    server.items["77"] = item

    result = _set_watch_state(_client(server), {"rating_key": "77"}, watched=False)

    assert item.mark_unwatched_calls == 1
    assert result["previous_watched"] is True
    assert result["watched"] is False
    assert result["scope"] == "item"


def test_show_mutation_reports_child_scope() -> None:
    server = FakeServer()
    server.items["9"] = FakeItem("9", "Resident Alien", "show", False)

    result = _set_watch_state(_client(server), {"rating_key": "9"}, watched=True)

    assert result["scope"] == "item_and_children"


def test_default_user_mutates_switched_user_context() -> None:
    accounts = [
        SimpleNamespace(id=1, name="Owner"),
        SimpleNamespace(id=7, name="Conor"),
    ]
    owner = FakeServer(accounts)
    conor = FakeServer()
    owner.switched["Conor"] = conor
    conor.items["42"] = FakeItem("42", "Alien", "movie", False)

    result = _set_watch_state(
        _client(owner, "7"),
        {"rating_key": "42"},
        watched=True,
    )

    assert owner.switch_calls == ["Conor"]
    assert result["user_id"] == 7
    assert result["user"] == "Conor"
    assert result["watched"] is True


def test_explicit_user_override_beats_configured_default() -> None:
    accounts = [
        SimpleNamespace(id=1, name="Owner"),
        SimpleNamespace(id=7, name="Conor"),
        SimpleNamespace(id=8, name="Guest"),
    ]
    owner = FakeServer(accounts)
    conor = FakeServer()
    guest = FakeServer()
    owner.switched = {"Conor": conor, "Guest": guest}
    guest.items["42"] = FakeItem("42", "Alien", "movie", False)

    result = _set_watch_state(
        _client(owner, "7"),
        {"rating_key": "42", "user_id": "8"},
        watched=True,
    )

    assert owner.switch_calls == ["Guest"]
    assert result["user_id"] == 8
    assert result["user"] == "Guest"


def test_unsupported_item_type_fails_without_silent_success() -> None:
    server = FakeServer()
    server.items["x"] = SimpleNamespace(ratingKey="x", title="Folder", type="directory")

    with pytest.raises(PlexExtendedError, match="does not support watched-state changes"):
        _set_watch_state(_client(server), {"rating_key": "x"}, watched=True)


def test_unconfirmed_server_state_is_an_error() -> None:
    server = FakeServer()
    server.items["42"] = IgnoringItem("42", "Alien", "movie", False)

    with pytest.raises(PlexExtendedError, match="did not confirm"):
        _set_watch_state(_client(server), {"rating_key": "42"}, watched=True)
