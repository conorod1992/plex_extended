"""Tests for Plex Extended recent-media windows and TV grouping."""

from __future__ import annotations

from datetime import datetime
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from zoneinfo import ZoneInfo

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
recent_module = _load_component_module("recent_media", "recent_media.py")

PlexExtendedClient = client_module.PlexExtendedClient
PlexExtendedError = client_module.PlexExtendedError
_recently_added = recent_module._recently_added
_recently_watched = recent_module._recently_watched
_window = recent_module._window


class FakeSection:
    def __init__(self, key: str, title: str, section_type: str) -> None:
        self.key = key
        self.title = title
        self.type = section_type
        self.items = []
        self.search_calls: list[dict[str, object]] = []
        self.recent_calls: list[dict[str, object]] = []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return list(self.items)[: kwargs.get("maxresults")]

    def recentlyAdded(self, maxresults=50, libtype=None):
        self.recent_calls.append({"maxresults": maxresults, "libtype": libtype})
        return [item for item in self.items if libtype is None or item.type == libtype][
            :maxresults
        ]


class FakeLibrary:
    def __init__(self, sections: list[FakeSection]) -> None:
        self._sections = sections

    def sections(self):
        return list(self._sections)

    def recentlyAdded(self):
        items = []
        for section in self._sections:
            items.extend(section.items)
        return sorted(items, key=lambda item: item.addedAt, reverse=True)


class FakeServer:
    def __init__(self, sections: list[FakeSection], history=None) -> None:
        self.library = FakeLibrary(sections)
        self.history = list(history or [])
        self.fetch_calls: list[dict[str, object]] = []

    def systemAccounts(self):
        return [SimpleNamespace(id=1, name="Owner")]

    def fetchItems(self, key, container_start=None, container_size=None, maxresults=None):
        start = int(container_start or 0)
        size = int(container_size or maxresults or len(self.history))
        self.fetch_calls.append({"key": key, "start": start, "size": size})
        return self.history[start : start + size]


def _client(server: FakeServer) -> PlexExtendedClient:
    client = object.__new__(PlexExtendedClient)
    client._server = server
    client.entry = SimpleNamespace(options={})
    client.hass = SimpleNamespace(config=SimpleNamespace(time_zone="Europe/Dublin"))
    return client


def _episode(
    title: str,
    season: int,
    number: int,
    added_at: datetime,
    *,
    watched: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        type="episode",
        title=title,
        ratingKey=f"e-{season}-{number}",
        librarySectionID=2,
        librarySectionTitle="TV Shows",
        grandparentTitle="Resident Alien",
        grandparentRatingKey="show-10",
        parentTitle=f"Season {season}",
        parentRatingKey=f"season-{season}",
        parentIndex=season,
        index=number,
        addedAt=added_at,
        viewCount=1 if watched else 0,
    )


def _movie(title: str, rating_key: str, added_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        type="movie",
        title=title,
        ratingKey=rating_key,
        librarySectionID=1,
        librarySectionTitle="Movies",
        addedAt=added_at,
        viewCount=0,
    )


def _history(title: str, viewed_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        type="movie",
        title=title,
        ratingKey=title,
        librarySectionID=1,
        librarySectionTitle="Movies",
        viewedAt=viewed_at,
        accountID=1,
        viewCount=1,
    )


def test_date_only_boundaries_use_home_assistant_timezone() -> None:
    client = _client(FakeServer([]))

    window = _window(client, {"since": "2026-09-07", "before": "2026-09-08"})

    assert window.since == datetime(2026, 9, 7, tzinfo=ZoneInfo("Europe/Dublin"))
    assert window.before == datetime(2026, 9, 8, tzinfo=ZoneInfo("Europe/Dublin"))
    assert window.since.utcoffset().total_seconds() == 3600


def test_within_days_cannot_be_mixed_with_absolute_window() -> None:
    client = _client(FakeServer([]))

    with pytest.raises(PlexExtendedError, match="cannot be combined"):
        _window(client, {"within_days": 7, "since": "2026-09-01"})


def test_recently_added_uses_server_side_date_filters() -> None:
    section = FakeSection("1", "Movies", "movie")
    section.items = [
        _movie("Alien", "1", datetime(2026, 9, 7, 12, tzinfo=ZoneInfo("UTC")))
    ]
    client = _client(FakeServer([section]))

    result = _recently_added(
        client,
        {
            "since": "2026-09-01",
            "before": "2026-09-08",
            "media_types": ["movie"],
            "limit": 10,
            "include_summary": False,
        },
    )

    assert result["count"] == 1
    filters = section.search_calls[0]["filters"]
    assert "addedAt>>" in filters
    assert "addedAt<<" in filters
    assert section.search_calls[0]["sort"] == "addedAt:desc"


def test_show_grouping_collapses_episode_imports() -> None:
    section = FakeSection("2", "TV Shows", "show")
    section.items = [
        _episode(
            "Pilot",
            1,
            1,
            datetime(2026, 9, 7, 20, tzinfo=ZoneInfo("UTC")),
            watched=True,
        ),
        _episode(
            "Homesick",
            1,
            2,
            datetime(2026, 9, 7, 19, tzinfo=ZoneInfo("UTC")),
        ),
        _episode(
            "Season Two",
            2,
            1,
            datetime(2026, 9, 7, 18, tzinfo=ZoneInfo("UTC")),
        ),
    ]
    client = _client(FakeServer([section]))

    result = _recently_added(
        client,
        {
            "group_tv_by": "show",
            "media_types": ["episode"],
            "limit": 10,
            "include_summary": False,
        },
    )

    assert result["count"] == 1
    assert result["media_item_count"] == 3
    group = result["results"][0]
    assert group["type"] == "show_addition_group"
    assert group["title"] == "Resident Alien"
    assert group["episodes_added"] == 3
    assert group["watched_episodes"] == 1
    assert group["remaining_episodes"] == 2
    assert group["seasons"] == [1, 2]
    assert group["latest_episode"]["title"] == "Pilot"
    assert section.recent_calls[0]["libtype"] == "episode"


def test_season_grouping_produces_distinct_season_rows() -> None:
    section = FakeSection("2", "TV Shows", "show")
    section.items = [
        _episode("One", 1, 1, datetime(2026, 9, 7, 20, tzinfo=ZoneInfo("UTC"))),
        _episode("Two", 1, 2, datetime(2026, 9, 7, 19, tzinfo=ZoneInfo("UTC"))),
        _episode("Three", 2, 1, datetime(2026, 9, 7, 18, tzinfo=ZoneInfo("UTC"))),
    ]
    result = _recently_added(
        _client(FakeServer([section])),
        {
            "group_tv_by": "season",
            "media_types": ["episode"],
            "limit": 10,
            "include_summary": False,
        },
    )

    assert result["count"] == 2
    assert [item["season"] for item in result["results"]] == [1, 2]
    assert result["results"][0]["episodes_added"] == 2


def test_history_honors_since_and_before_while_paging() -> None:
    utc = ZoneInfo("UTC")
    section = FakeSection("1", "Movies", "movie")
    history = [
        _history("Too New", datetime(2026, 9, 7, 20, tzinfo=utc)),
        _history("Inside A", datetime(2026, 9, 7, 17, tzinfo=utc)),
        _history("Inside B", datetime(2026, 9, 7, 16, tzinfo=utc)),
        _history("Too Old", datetime(2026, 9, 7, 12, tzinfo=utc)),
    ]
    server = FakeServer([section], history)

    result = _recently_watched(
        _client(server),
        {
            "since": "2026-09-07T15:00:00+00:00",
            "before": "2026-09-07T18:00:00+00:00",
            "media_types": ["movie"],
            "limit": 10,
            "include_summary": False,
        },
    )

    assert [item["title"] for item in result["results"]] == ["Inside A", "Inside B"]
    assert "viewedAt%3E" in server.fetch_calls[0]["key"]
    assert result["window"]["since"].startswith("2026-09-07T16:00:00+01:00")
    assert result["window"]["before"].startswith("2026-09-07T19:00:00+01:00")
