"""Tests for Plex Extended TV catch-up queries."""

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
_load_component_module("recent_media")
_load_component_module("viewing_progress")
catch_up_module = _load_component_module("tv_catch_up")

PlexExtendedClient = client_module.PlexExtendedClient
PlexExtendedError = client_module.PlexExtendedError
_tv_catch_up = catch_up_module._tv_catch_up
_CANDIDATE_SCAN_LIMIT = catch_up_module._CANDIDATE_SCAN_LIMIT


class FakeSection:
    def __init__(self, key: str, title: str, section_type: str = "show") -> None:
        self.key = key
        self.title = title
        self.type = section_type
        self.items: list[SimpleNamespace] = []
        self.search_calls: list[dict[str, object]] = []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return list(self.items)[: int(kwargs.get("maxresults", len(self.items)))]


class FakeLibrary:
    def __init__(self, sections: list[FakeSection]) -> None:
        self._sections = sections

    def sections(self):
        return list(self._sections)


class FakeServer:
    def __init__(self, sections: list[FakeSection]) -> None:
        self.library = FakeLibrary(sections)

    def systemAccounts(self):
        return [SimpleNamespace(id=1, name="Owner")]


def _client(server: FakeServer) -> PlexExtendedClient:
    client = object.__new__(PlexExtendedClient)
    client._server = server
    client.entry = SimpleNamespace(options={})
    client.hass = SimpleNamespace(config=SimpleNamespace(time_zone="Europe/Dublin"))
    return client


def _episode(
    show: str,
    show_key: str,
    season: int,
    number: int,
    added_at: datetime,
    *,
    rating_key: str | None = None,
    watched: bool = False,
    progress: bool = False,
    library_id: int = 2,
) -> SimpleNamespace:
    duration = 2_400_000
    return SimpleNamespace(
        type="episode",
        title=f"{show} {season}x{number}",
        ratingKey=rating_key or f"{show_key}-{season}-{number}",
        librarySectionID=library_id,
        librarySectionTitle="TV Shows",
        grandparentTitle=show,
        grandparentRatingKey=show_key,
        parentTitle=f"Season {season}",
        parentRatingKey=f"{show_key}-season-{season}",
        parentIndex=season,
        index=number,
        addedAt=added_at,
        duration=duration,
        viewOffset=duration // 2 if progress else 0,
        viewCount=1 if watched else 0,
        isPlayed=watched,
    )


def test_groups_remaining_episodes_by_show_and_preserves_canonical_order() -> None:
    zone = ZoneInfo("UTC")
    section = FakeSection("2", "TV Shows")
    section.items = [
        _episode("Resident Alien", "show-a", 2, 1, datetime(2026, 9, 8, 9, tzinfo=zone)),
        _episode("Resident Alien", "show-a", 1, 3, datetime(2026, 9, 8, 10, tzinfo=zone)),
        _episode("Foundation", "show-b", 1, 2, datetime(2026, 9, 7, 10, tzinfo=zone), progress=True),
    ]

    result = _tv_catch_up(_client(FakeServer([section])), {"limit": 10})

    assert result["count"] == 2
    assert result["matched_show_count"] == 2
    assert result["remaining_episode_count"] == 3
    assert result["unwatched_episode_count"] == 2
    assert result["in_progress_episode_count"] == 1
    resident = result["results"][0]
    assert resident["title"] == "Resident Alien"
    assert resident["remaining_episode_count"] == 2
    assert resident["show_rating_key"] == "show-a"
    assert [item["season_episode"] for item in resident["episodes"]] == [
        "S01E03",
        "S02E01",
    ]
    assert resident["next_episode"]["season_episode"] == "S01E03"


def test_server_query_uses_unwatched_and_shared_added_window_filters() -> None:
    zone = ZoneInfo("UTC")
    section = FakeSection("2", "TV Shows")
    section.items = [
        _episode("Example", "show-a", 1, 1, datetime(2026, 9, 7, 12, tzinfo=zone))
    ]

    result = _tv_catch_up(
        _client(FakeServer([section])),
        {"since": "2026-09-01", "before": "2026-09-08"},
    )

    filters = section.search_calls[0]["filters"]
    assert filters["unwatched"] is True
    assert "addedAt>>" in filters
    assert "addedAt<<" in filters
    assert section.search_calls[0]["sort"] == "addedAt:desc"
    assert section.search_calls[0]["libtype"] == "episode"
    assert result["window"]["since"].startswith("2026-09-01T00:00:00")
    assert result["window"]["before"].startswith("2026-09-08T00:00:00")


def test_backend_rechecks_watched_state_and_exact_window() -> None:
    zone = ZoneInfo("Europe/Dublin")
    section = FakeSection("2", "TV Shows")
    section.items = [
        _episode("Kept", "show-a", 1, 1, datetime(2026, 9, 7, 12, tzinfo=zone)),
        _episode("Watched", "show-b", 1, 1, datetime(2026, 9, 7, 13, tzinfo=zone), watched=True),
        _episode("Too old", "show-c", 1, 1, datetime(2026, 8, 31, 23, tzinfo=zone)),
        _episode("At before", "show-d", 1, 1, datetime(2026, 9, 8, 0, tzinfo=zone)),
    ]

    result = _tv_catch_up(
        _client(FakeServer([section])),
        {"since": "2026-09-01", "before": "2026-09-08"},
    )

    assert [group["title"] for group in result["results"]] == ["Kept"]
    assert result["remaining_episode_count"] == 1


def test_in_progress_and_specials_are_explicitly_controllable() -> None:
    zone = ZoneInfo("UTC")
    section = FakeSection("2", "TV Shows")
    section.items = [
        _episode("Example", "show-a", 0, 1, datetime(2026, 9, 8, 10, tzinfo=zone)),
        _episode("Example", "show-a", 1, 1, datetime(2026, 9, 8, 9, tzinfo=zone), progress=True),
        _episode("Example", "show-a", 1, 2, datetime(2026, 9, 8, 8, tzinfo=zone)),
    ]
    client = _client(FakeServer([section]))

    default = _tv_catch_up(client, {})
    assert default["remaining_episode_count"] == 2
    assert default["in_progress_episode_count"] == 1
    assert default["results"][0]["seasons"] == [1]

    strict = _tv_catch_up(
        client,
        {"include_specials": True, "include_in_progress": False},
    )
    assert strict["remaining_episode_count"] == 2
    assert strict["in_progress_episode_count"] == 0
    assert strict["results"][0]["seasons"] == [0, 1]


def test_group_and_episode_limits_report_truncation_without_changing_counts() -> None:
    zone = ZoneInfo("UTC")
    section = FakeSection("2", "TV Shows")
    section.items = [
        _episode("A", "show-a", 1, 1, datetime(2026, 9, 8, 12, tzinfo=zone)),
        _episode("A", "show-a", 1, 2, datetime(2026, 9, 8, 11, tzinfo=zone)),
        _episode("B", "show-b", 1, 1, datetime(2026, 9, 7, 12, tzinfo=zone)),
    ]

    result = _tv_catch_up(
        _client(FakeServer([section])),
        {"limit": 1, "episode_limit": 1},
    )

    assert result["count"] == 1
    assert result["matched_show_count"] == 2
    assert result["remaining_episode_count"] == 3
    assert result["results_truncated"] is True
    assert result["results"][0]["remaining_episode_count"] == 2
    assert result["results"][0]["episodes_returned"] == 1
    assert result["results"][0]["episodes_truncated"] is True


def test_non_tv_selected_library_is_rejected() -> None:
    section = FakeSection("1", "Movies", section_type="movie")
    client = _client(FakeServer([section]))

    with pytest.raises(PlexExtendedError, match="not a TV-show library"):
        _tv_catch_up(client, {"library_id": "1"})


def test_candidate_scan_truncation_is_explicit() -> None:
    zone = ZoneInfo("UTC")
    section = FakeSection("2", "TV Shows")
    section.items = [
        _episode(
            "Big Show",
            "show-big",
            1,
            index + 1,
            datetime(2026, 9, 8, 12, tzinfo=zone),
            rating_key=str(index + 1),
        )
        for index in range(_CANDIDATE_SCAN_LIMIT + 1)
    ]

    result = _tv_catch_up(_client(FakeServer([section])), {"episode_limit": 1})

    assert result["candidate_scan_truncated"] is True
    assert result["candidate_scan_limit_per_library"] == _CANDIDATE_SCAN_LIMIT
    assert result["remaining_episode_count"] == _CANDIDATE_SCAN_LIMIT
