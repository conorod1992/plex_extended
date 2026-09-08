"""Tests for Plex Extended aggregate library summaries."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from xml.etree.ElementTree import Element

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

const_module = _load_component_module("const", "const.py")
client_module = _load_component_module("client", "client.py")
_load_component_module("user_context", "user_context.py")
_load_component_module("library_query", "library_query.py")
summary_module = _load_component_module("library_summary", "library_summary.py")

PlexExtendedClient = client_module.PlexExtendedClient
_library_summary = summary_module._library_summary


class FakeSection:
    def __init__(self, key="1", title="Movies", section_type="movie") -> None:
        self.key = key
        self.title = title
        self.type = section_type
        self._server = None
        self.search_results = []
        self.search_calls = []
        self.build_calls = []

    def _buildSearchKey(self, **kwargs):
        self.build_calls.append(kwargs)
        return f"/library/sections/{self.key}/all?type=1"

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return list(self.search_results)


class FakeLibrary:
    def __init__(self, sections):
        self._sections = list(sections)

    def sections(self):
        return list(self._sections)


class FakeServer:
    def __init__(self, sections, *, total_size=0, accounts=None) -> None:
        self.library = FakeLibrary(sections)
        self.total_size = total_size
        self.query_calls = []
        self.fetch_batches = []
        self.full_items = {}
        self.accounts = accounts or []
        self.switched = {}
        self.switch_calls = []
        for section in sections:
            section._server = self

    def query(self, key, headers=None):
        self.query_calls.append((key, dict(headers or {})))
        attrs = {}
        if self.total_size is not None:
            attrs["totalSize"] = str(self.total_size)
        return Element("MediaContainer", attrs)

    def fetchItems(self, keys):
        self.fetch_batches.append(list(keys))
        return [self.full_items[str(key)] for key in keys if str(key) in self.full_items]

    def systemAccounts(self):
        return list(self.accounts)

    def switchUser(self, name):
        self.switch_calls.append(str(name))
        return self.switched[str(name)]


def _client(server, default_user_id=None):
    client = object.__new__(PlexExtendedClient)
    client._server = server
    options = {}
    if default_user_id is not None:
        options[const_module.CONF_DEFAULT_USER_ID] = str(default_user_id)
    client.entry = SimpleNamespace(options=options)
    return client


def _partial(rating_key):
    return SimpleNamespace(ratingKey=str(rating_key), type="movie")


def _full_item(
    rating_key,
    *,
    year,
    genres,
    resolutions,
    watched=False,
    view_offset=0,
    duration_minutes=100,
    content_rating="R",
    studio="Studio",
    collections=(),
):
    return SimpleNamespace(
        ratingKey=str(rating_key),
        type="movie",
        year=year,
        genres=[SimpleNamespace(tag=value) for value in genres],
        collections=[SimpleNamespace(tag=value) for value in collections],
        media=[SimpleNamespace(videoResolution=value) for value in resolutions],
        isPlayed=watched,
        viewCount=1 if watched else 0,
        viewOffset=view_offset,
        duration=duration_minutes * 60_000,
        contentRating=content_rating,
        studio=studio,
    )


def test_count_only_uses_plex_total_size_without_materializing_items() -> None:
    section = FakeSection()
    server = FakeServer([section], total_size=137)
    result = _library_summary(
        _client(server),
        {
            "media_type": "movie",
            "genres": ["Horror"],
            "watched_state": "unwatched",
            "hdr": "any",
        },
    )

    assert result["count"] == 137
    assert result["library"] == "Movies"
    assert section.search_calls == []
    assert server.fetch_batches == []
    assert server.query_calls[0][1] == {
        "X-Plex-Container-Start": "0",
        "X-Plex-Container-Size": "1",
    }
    assert section.build_calls[0]["filters"] == {
        "genre": ["Horror"],
        "unwatched": True,
    }


def test_client_side_range_filter_forces_exact_materialized_count() -> None:
    section = FakeSection()
    section.search_results = [_partial(1), _partial(2)]
    server = FakeServer([section], total_size=50)

    result = _library_summary(
        _client(server),
        {
            "media_type": "movie",
            "critic_rating_min": 7.5,
            "watched_state": "any",
            "hdr": "any",
        },
    )

    assert result["count"] == 2
    assert server.query_calls == []
    assert section.search_calls[0]["rating__gte"] == 7.5


def test_facets_are_exact_compact_and_multi_value_aware() -> None:
    section = FakeSection()
    section.search_results = [_partial(1), _partial(2), _partial(3)]
    server = FakeServer([section], total_size=3)
    server.full_items = {
        "1": _full_item(
            1,
            year=1982,
            genres=["Horror", "Science Fiction"],
            resolutions=["4k", "1080"],
            watched=True,
            duration_minutes=120,
            studio="Fox",
            collections=["Alien"],
        ),
        "2": _full_item(
            2,
            year=1986,
            genres=["Horror"],
            resolutions=["1080"],
            view_offset=600_000,
            duration_minutes=100,
            studio="Fox",
            collections=["Alien"],
        ),
        "3": _full_item(
            3,
            year=1990,
            genres=["Comedy"],
            resolutions=["720"],
            duration_minutes=90,
            content_rating="PG",
            studio="Other",
        ),
    }

    result = _library_summary(
        _client(server),
        {
            "media_type": "movie",
            "watched_state": "any",
            "hdr": "any",
            "facets": [
                "genre",
                "decade",
                "resolution",
                "watched_state",
                "content_rating",
                "studio",
                "collection",
            ],
            "facet_limit": 2,
            "include_total_duration": True,
        },
    )

    assert result["count"] == 3
    assert result["total_duration_minutes"] == 310.0
    assert result["duration_items"] == 3
    assert result["duration_missing_items"] == 0
    assert server.fetch_batches == [[1, 2, 3]]

    genre = result["facets"]["genre"]
    assert genre["values"][0] == {"value": "Horror", "count": 2}
    assert genre["total_values"] == 3
    assert genre["truncated"] is True

    decade = result["facets"]["decade"]
    assert decade["values"][0] == {"value": "1980s", "count": 2}
    assert decade["values"][1] == {"value": "1990s", "count": 1}

    resolution = result["facets"]["resolution"]
    assert resolution["values"][0] == {"value": "1080", "count": 2}
    assert resolution["total_values"] == 3

    watched = result["facets"]["watched_state"]
    assert watched["total_values"] == 3
    assert watched["truncated"] is True
    assert {row["value"] for row in watched["values"]}.issubset(
        {"watched", "in_progress", "unwatched"}
    )

    assert result["facets"]["content_rating"]["values"][0] == {
        "value": "R",
        "count": 2,
    }
    assert result["facets"]["studio"]["values"][0] == {
        "value": "Fox",
        "count": 2,
    }
    assert result["facets"]["collection"]["values"][0] == {
        "value": "Alien",
        "count": 2,
    }
    assert result["facets"]["collection"]["missing_items"] == 1


def test_default_user_context_drives_summary_query() -> None:
    owner_section = FakeSection()
    user_section = FakeSection()
    accounts = [
        SimpleNamespace(id=1, name="Owner"),
        SimpleNamespace(id=7, name="Conor"),
    ]
    owner = FakeServer([owner_section], total_size=99, accounts=accounts)
    conor = FakeServer([user_section], total_size=7)
    owner.switched["Conor"] = conor

    result = _library_summary(
        _client(owner, default_user_id=7),
        {
            "media_type": "movie",
            "watched_state": "unwatched",
            "hdr": "any",
        },
    )

    assert result["count"] == 7
    assert owner.switch_calls == ["Conor"]
    assert owner.query_calls == []
    assert len(conor.query_calls) == 1
    assert result["plex_user"] == "Conor"
    assert result["plex_user_id"] == "7"


def test_missing_total_size_falls_back_to_exact_materialized_count() -> None:
    section = FakeSection()
    section.search_results = [_partial(1), _partial(2), _partial(3)]
    server = FakeServer([section], total_size=None)

    result = _library_summary(
        _client(server),
        {"media_type": "movie", "watched_state": "any", "hdr": "any"},
    )

    assert result["count"] == 3
    assert len(server.query_calls) == 1
    assert len(section.search_calls) == 1
