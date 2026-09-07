"""Focused unit tests for Plex Extended query hardening."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest


ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"


def _install_homeassistant_stubs() -> None:
    """Install the tiny subset of Home Assistant modules client.py imports."""
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
    """Load a component module without executing the integration __init__.py."""
    full_name = f"custom_components.plex_extended.{name}"
    spec = importlib.util.spec_from_file_location(full_name, COMPONENT / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


_install_homeassistant_stubs()

custom_components = ModuleType("custom_components")
custom_components.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", custom_components)

package = ModuleType("custom_components.plex_extended")
package.__path__ = [str(COMPONENT)]
sys.modules.setdefault("custom_components.plex_extended", package)

const = _load_component_module("const", "const.py")
client_module = _load_component_module("client", "client.py")

PlexExtendedClient = client_module.PlexExtendedClient
PlexExtendedError = client_module.PlexExtendedError


class FakeSection:
    """Minimal Plex library section."""

    def __init__(self, key: str, title: str, section_type: str = "movie") -> None:
        self.key = key
        self.title = title
        self.type = section_type


class FakeLibrary:
    """Minimal Plex library container."""

    def __init__(self, sections: list[FakeSection] | None = None) -> None:
        self._sections = sections or []

    def sections(self) -> list[FakeSection]:
        return self._sections


class FakeServer:
    """Minimal Plex server supporting the query methods under test."""

    def __init__(
        self,
        *,
        search_results: list[SimpleNamespace] | None = None,
        history: list[SimpleNamespace] | None = None,
        sections: list[FakeSection] | None = None,
        accounts: list[SimpleNamespace] | None = None,
    ) -> None:
        self.library = FakeLibrary(sections)
        self.search_results = search_results or []
        self.history = history or []
        self.accounts = accounts or []
        self.search_calls: list[dict[str, object]] = []
        self.fetch_calls: list[dict[str, object]] = []

    def search(self, query, mediatype=None, limit=None, sectionId=None):
        self.search_calls.append(
            {
                "query": query,
                "mediatype": mediatype,
                "limit": limit,
                "sectionId": sectionId,
            }
        )
        return self.search_results

    def fetchItems(
        self,
        key,
        container_start=None,
        container_size=None,
        maxresults=None,
    ):
        start = int(container_start or 0)
        size = int(container_size or maxresults or len(self.history))
        self.fetch_calls.append(
            {
                "key": key,
                "container_start": start,
                "container_size": size,
                "maxresults": maxresults,
            }
        )
        return self.history[start : start + size]

    def systemAccounts(self):
        return self.accounts


def _item(
    title: str,
    media_type: str,
    rating_key: str,
    *,
    library_id: int = 1,
    account_id: int | None = None,
) -> SimpleNamespace:
    """Create a compact fake Plex media item."""
    return SimpleNamespace(
        title=title,
        type=media_type,
        ratingKey=rating_key,
        librarySectionID=library_id,
        viewCount=0,
        accountID=account_id,
    )


def _client(server: FakeServer) -> PlexExtendedClient:
    """Create a client instance for synchronous private-method testing."""
    client = object.__new__(PlexExtendedClient)
    client._server = server
    return client


def test_mixed_search_uses_one_hub_query_and_preserves_plex_order() -> None:
    """Mixed search must not privilege the first requested media type."""
    server = FakeServer(
        search_results=[
            _item("Resident Alien", "show", "10"),
            SimpleNamespace(type="actor", title="Alien Actor"),
            _item("Alien", "movie", "11"),
        ]
    )

    result = _client(server)._search(
        "Alien",
        ["movie", "show"],
        10,
        None,
        False,
        False,
    )

    assert [item["title"] for item in result["results"]] == [
        "Resident Alien",
        "Alien",
    ]
    assert len(server.search_calls) == 1
    assert server.search_calls[0]["mediatype"] is None


def test_single_type_search_keeps_native_plex_type_filter() -> None:
    """Single-type search should remain efficient."""
    server = FakeServer(search_results=[_item("Alien", "movie", "11")])

    _client(server)._search(
        "Alien",
        ["movie"],
        10,
        None,
        False,
        False,
    )

    assert server.search_calls[0]["mediatype"] == "movie"


def test_duplicate_library_names_require_library_id() -> None:
    """Name lookup must fail rather than silently picking the wrong library."""
    sections = [
        FakeSection("1", "Movies"),
        FakeSection("2", "Movies"),
    ]
    client = _client(FakeServer(sections=sections))

    with pytest.raises(PlexExtendedError, match="Use library_id instead"):
        client._section("Movies")

    assert client._section(library_id="2") is sections[1]


def test_filtered_history_pages_until_requested_results_are_filled() -> None:
    """Media-type filtering must continue past a TV-heavy first history page."""
    history = [
        _item(f"Episode {index}", "episode", str(index)) for index in range(120)
    ] + [
        _item("Alien", "movie", "200"),
        _item("Aliens", "movie", "201"),
        _item("Alien 3", "movie", "202"),
    ]
    server = FakeServer(history=history)

    result = _client(server)._recently_watched(
        2,
        None,
        None,
        ["movie"],
        False,
    )

    assert [item["title"] for item in result["results"]] == ["Alien", "Aliens"]
    assert [call["container_start"] for call in server.fetch_calls] == [0, 100]


def test_history_accepts_stable_library_and_user_ids() -> None:
    """Stable IDs should flow into the Plex history request exactly."""
    section = FakeSection("2", "TV Shows", "show")
    server = FakeServer(
        history=[_item("Pilot", "episode", "300", library_id=2, account_id=7)],
        sections=[section],
        accounts=[SimpleNamespace(id=7, name="Conor")],
    )

    result = _client(server)._recently_watched(
        1,
        None,
        None,
        ["episode"],
        False,
        "2",
        "7",
    )

    query = parse_qs(urlsplit(server.fetch_calls[0]["key"]).query)
    assert query["librarySectionID"] == ["2"]
    assert query["accountID"] == ["7"]
    assert result["results"][0]["user"] == "Conor"


def test_llm_summaries_default_off() -> None:
    """LLM list/search responses should default to compact payloads."""
    assert const.DEFAULT_LLM_INCLUDE_SUMMARY is False
