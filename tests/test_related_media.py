"""Tests for Plex Extended related-media queries."""

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


def _load_component_module(name: str) -> ModuleType:
    full_name = f"custom_components.plex_extended.{name}"
    existing = sys.modules.get(full_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(full_name, COMPONENT / f"{name}.py")
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

_load_component_module("const")
client_module = _load_component_module("client")
_load_component_module("user_context")
related_module = _load_component_module("related_media")

PlexExtendedClient = client_module.PlexExtendedClient
PlexExtendedError = client_module.PlexExtendedError
_related_media = related_module._related_media


class FakeSection:
    def __init__(self, key: str, title: str, section_type: str) -> None:
        self.key = key
        self.title = title
        self.type = section_type


class FakeLibrary:
    def __init__(self, sections: list[FakeSection]) -> None:
        self._sections = sections

    def sections(self):
        return list(self._sections)


class FakeServer:
    def __init__(self, source, sections: list[FakeSection] | None = None) -> None:
        self.source = source
        self.library = FakeLibrary(
            sections or [FakeSection("1", "Movies", "movie")]
        )
        self.fetch_calls: list[str] = []

    def fetchItem(self, rating_key):
        self.fetch_calls.append(str(rating_key))
        if str(rating_key) != str(self.source.ratingKey):
            raise RuntimeError("not found")
        return self.source

    def systemAccounts(self):
        return [SimpleNamespace(id=1, name="Owner")]


def _client(server: FakeServer) -> PlexExtendedClient:
    client = object.__new__(PlexExtendedClient)
    client._server = server
    client.entry = SimpleNamespace(options={})
    client.hass = SimpleNamespace()
    return client


def _item(
    rating_key: str | int | None,
    title: str,
    *,
    media_type: str = "movie",
    library_id: int | None = 1,
    watched: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        ratingKey=rating_key,
        type=media_type,
        title=title,
        year=2025,
        librarySectionID=library_id,
        librarySectionTitle="Movies" if library_id is not None else None,
        viewCount=1 if watched else 0,
    )


def _hub(
    title: str,
    items: list[SimpleNamespace],
    *,
    identifier: str | None = None,
    more: bool = False,
    size: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        hubIdentifier=identifier,
        context="hub.related",
        type="movie",
        size=len(items) if size is None else size,
        more=more,
        items=items,
    )


def _source(hubs, *, media_type: str = "movie", library_id: int = 1):
    source = _item("10", "Alien", media_type=media_type, library_id=library_id)
    source.hubs = lambda: list(hubs)
    return source


def test_preserves_plex_hub_provenance_and_order() -> None:
    source = _source(
        [
            _hub(
                "Related Movies",
                [_item("11", "Aliens"), _item("12", "The Thing")],
                identifier="related.movies",
            ),
            _hub(
                "More with Sigourney Weaver",
                [_item("13", "Galaxy Quest")],
                identifier="actor.sigourney-weaver",
            ),
        ]
    )
    result = _related_media(_client(FakeServer(source)), {"rating_key": "10"})

    assert result["success"] is True
    assert result["source"]["rating_key"] == "10"
    assert [hub["title"] for hub in result["hubs"]] == [
        "Related Movies",
        "More with Sigourney Weaver",
    ]
    assert [item["title"] for item in result["hubs"][0]["results"]] == [
        "Aliens",
        "The Thing",
    ]
    assert result["hubs"][0]["identifier"] == "related.movies"


def test_filters_external_non_media_and_source_items() -> None:
    source = _source(
        [
            _hub(
                "Related Movies",
                [
                    _item("10", "Alien"),
                    _item("11", "Local"),
                    _item("12", "Online", library_id=None),
                    _item("13", "Person", media_type="person"),
                    _item(None, "No ID"),
                ],
            )
        ]
    )

    result = _related_media(_client(FakeServer(source)), {"rating_key": "10"})

    assert result["result_item_count"] == 1
    assert [item["title"] for item in result["hubs"][0]["results"]] == ["Local"]


def test_deduplicates_inside_one_hub_but_preserves_cross_hub_provenance() -> None:
    duplicate = _item("11", "Aliens")
    source = _source(
        [
            _hub("Related Movies", [duplicate, duplicate]),
            _hub("Same Director", [duplicate]),
        ]
    )

    result = _related_media(_client(FakeServer(source)), {"rating_key": "10"})

    assert result["result_item_count"] == 2
    assert result["hubs"][0]["count"] == 1
    assert result["hubs"][1]["count"] == 1


def test_item_limit_and_plex_more_are_explicit() -> None:
    source = _source(
        [
            _hub(
                "Related Movies",
                [_item("11", "One"), _item("12", "Two"), _item("13", "Three")],
                more=True,
                size=20,
            )
        ]
    )

    result = _related_media(
        _client(FakeServer(source)),
        {"rating_key": "10", "item_limit": 2},
    )
    hub = result["hubs"][0]

    assert hub["declared_size"] == 20
    assert hub["local_item_count_in_loaded_hub"] == 3
    assert hub["count"] == 2
    assert hub["more_available_from_plex"] is True
    assert hub["results_truncated"] is True


def test_hub_limit_counts_only_hubs_with_local_results() -> None:
    source = _source(
        [
            _hub("External", [_item("20", "Online", library_id=None)]),
            _hub("First", [_item("11", "One")]),
            _hub("Second", [_item("12", "Two")]),
        ]
    )

    result = _related_media(
        _client(FakeServer(source)),
        {"rating_key": "10", "hub_limit": 1},
    )

    assert result["plex_hub_count"] == 3
    assert result["matched_hub_count"] == 2
    assert result["count"] == 1
    assert result["hubs_truncated"] is True
    assert result["hubs"][0]["title"] == "First"


def test_selected_library_must_contain_source() -> None:
    source = _source([])
    server = FakeServer(
        source,
        sections=[
            FakeSection("1", "Movies", "movie"),
            FakeSection("2", "Other Movies", "movie"),
        ],
    )

    with pytest.raises(PlexExtendedError, match="not in library 'Other Movies'"):
        _related_media(
            _client(server),
            {"rating_key": "10", "library_id": "2"},
        )


def test_non_movie_show_source_is_rejected() -> None:
    source = _source([], media_type="episode")

    with pytest.raises(PlexExtendedError, match="supports movies and TV shows"):
        _related_media(_client(FakeServer(source)), {"rating_key": "10"})


@pytest.mark.parametrize("rating_key", ["", "0", "-1", "abc", None])
def test_rating_key_must_be_positive_numeric(rating_key) -> None:
    source = _source([])

    with pytest.raises(PlexExtendedError, match="positive local Plex numeric ID"):
        _related_media(_client(FakeServer(source)), {"rating_key": rating_key})


def test_include_summary_is_forwarded_to_source_and_results() -> None:
    related = _item("11", "Aliens")
    related.summary = " sequel "
    source = _source([_hub("Related Movies", [related])])
    source.summary = " original "

    result = _related_media(
        _client(FakeServer(source)),
        {"rating_key": "10", "include_summary": False},
    )

    assert "summary" not in result["source"]
    assert "summary" not in result["hubs"][0]["results"][0]
