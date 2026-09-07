"""Tests for Plex Extended TV viewing progress."""

from __future__ import annotations

from datetime import datetime
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

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
    """Load a component module without executing integration __init__.py."""
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

_load_component_module("const", "const.py")
client_module = _load_component_module("client", "client.py")
progress_module = _load_component_module("viewing_progress", "viewing_progress.py")

PlexExtendedClient = client_module.PlexExtendedClient
PlexExtendedError = client_module.PlexExtendedError
_watch_status = progress_module._watch_status
_resolve_show = progress_module._resolve_show


class FakeSection:
    """Minimal Plex section."""

    def __init__(self, key: str, title: str, section_type: str = "show") -> None:
        self.key = key
        self.title = title
        self.type = section_type


class FakeLibrary:
    """Minimal Plex library."""

    def __init__(self, sections: list[FakeSection]) -> None:
        self._sections = sections

    def sections(self) -> list[FakeSection]:
        return self._sections


class FakeShow:
    """Minimal Plex show with episode state."""

    type = "show"

    def __init__(
        self,
        title: str,
        rating_key: str,
        episodes: list[SimpleNamespace],
        *,
        year: int = 2021,
        library_id: int = 2,
        on_deck: SimpleNamespace | None = None,
    ) -> None:
        self.title = title
        self.ratingKey = rating_key
        self.year = year
        self.librarySectionID = library_id
        self.librarySectionTitle = "TV Shows"
        self.viewCount = 0
        self._episodes = episodes
        self._on_deck = on_deck

    def episodes(self):
        return list(self._episodes)

    def onDeck(self):
        return self._on_deck


class FakeServer:
    """Minimal Plex server."""

    def __init__(
        self,
        shows: list[FakeShow],
        sections: list[FakeSection] | None = None,
    ) -> None:
        self.shows = shows
        self.library = FakeLibrary(sections or [FakeSection("2", "TV Shows")])
        self.search_calls: list[dict[str, object]] = []

    def fetchItem(self, rating_key):
        for show in self.shows:
            if str(show.ratingKey) == str(rating_key):
                return show
        return SimpleNamespace(type="movie", ratingKey=rating_key, title="Not a show")

    def search(self, query, mediatype=None, limit=None, sectionId=None):
        self.search_calls.append(
            {
                "query": query,
                "mediatype": mediatype,
                "limit": limit,
                "sectionId": sectionId,
            }
        )
        return [
            show
            for show in self.shows
            if sectionId is None or str(show.librarySectionID) == str(sectionId)
        ]


def _episode(
    season: int,
    number: int,
    title: str,
    *,
    watched: bool = False,
    offset: int = 0,
    last_viewed: datetime | None = None,
) -> SimpleNamespace:
    duration = 2_400_000
    return SimpleNamespace(
        type="episode",
        title=title,
        ratingKey=f"{season}-{number}",
        librarySectionID=2,
        librarySectionTitle="TV Shows",
        parentTitle=f"Season {season}",
        grandparentTitle="Resident Alien",
        parentIndex=season,
        index=number,
        duration=duration,
        viewOffset=offset,
        viewCount=1 if watched else 0,
        isPlayed=watched,
        lastViewedAt=last_viewed,
    )


def _client(server: FakeServer) -> PlexExtendedClient:
    client = object.__new__(PlexExtendedClient)
    client._server = server
    return client


def test_watch_status_reports_current_and_next_episode() -> None:
    """Partially watched shows expose counts and Plex's On Deck episode."""
    ep1 = _episode(
        1,
        1,
        "Pilot",
        watched=True,
        last_viewed=datetime(2026, 9, 1, 20, 0),
    )
    ep2 = _episode(
        1,
        2,
        "Homesick",
        offset=1_200_000,
        last_viewed=datetime(2026, 9, 6, 21, 0),
    )
    ep3 = _episode(1, 3, "Secrets")
    show = FakeShow("Resident Alien", "10", [ep1, ep2, ep3], on_deck=ep2)

    result = _watch_status(
        _client(FakeServer([show])),
        {"rating_key": "10", "include_summary": False, "include_seasons": True},
    )

    assert result["status"] == "in_progress"
    assert result["watched_episodes"] == 1
    assert result["unwatched_episodes"] == 2
    assert result["in_progress_episodes"] == 1
    assert result["completion_percent"] == 33.3
    assert result["last_watched_episode"]["season_episode"] == "S01E01"
    assert result["last_activity_episode"]["season_episode"] == "S01E02"
    assert result["in_progress_episode"]["progress_percent"] == 50.0
    assert result["next_episode"]["season_episode"] == "S01E02"
    assert result["seasons"][0]["complete"] is False


def test_complete_show_has_no_next_episode() -> None:
    """A fully watched show reports completion and no next episode."""
    ep1 = _episode(1, 1, "Pilot", watched=True)
    ep2 = _episode(1, 2, "Finale", watched=True)
    show = FakeShow("Complete Show", "20", [ep1, ep2], on_deck=None)

    result = _watch_status(
        _client(FakeServer([show])),
        {"rating_key": "20", "include_summary": False},
    )

    assert result["status"] == "complete"
    assert result["complete"] is True
    assert result["completion_percent"] == 100.0
    assert result["next_episode"] is None


def test_specials_are_excluded_by_default() -> None:
    """Unwatched season-zero items must not stop an otherwise complete show."""
    special = _episode(0, 1, "Holiday Special")
    regular = _episode(1, 1, "Pilot", watched=True)
    show = FakeShow("Special Show", "30", [special, regular], on_deck=special)
    client = _client(FakeServer([show]))

    default = _watch_status(client, {"rating_key": "30", "include_summary": False})
    included = _watch_status(
        client,
        {
            "rating_key": "30",
            "include_summary": False,
            "include_specials": True,
        },
    )

    assert default["complete"] is True
    assert default["total_episodes"] == 1
    assert included["complete"] is False
    assert included["total_episodes"] == 2
    assert included["next_episode"]["season_episode"] == "S00E01"


def test_title_resolution_prefers_exact_match_and_year() -> None:
    """Title + year can resolve remakes without a rating key."""
    old = FakeShow("The Show", "40", [], year=1999)
    new = FakeShow("The Show", "41", [], year=2026)
    client = _client(FakeServer([old, new]))

    resolved = _resolve_show(
        client,
        rating_key=None,
        title="The Show",
        year=2026,
        library=None,
        library_id=None,
    )

    assert resolved.ratingKey == "41"


def test_ambiguous_exact_titles_require_stable_identifier() -> None:
    """Duplicate exact title/year matches must not be guessed."""
    first = FakeShow("The Show", "50", [], year=2026)
    second = FakeShow("The Show", "51", [], year=2026)
    client = _client(FakeServer([first, second]))

    with pytest.raises(PlexExtendedError, match="Multiple Plex shows exactly match"):
        _resolve_show(
            client,
            rating_key=None,
            title="The Show",
            year=2026,
            library=None,
            library_id=None,
        )


def test_rating_key_must_refer_to_show() -> None:
    """A movie/episode rating key cannot silently become a TV progress query."""
    client = _client(FakeServer([]))

    with pytest.raises(PlexExtendedError, match="is not a TV show"):
        _resolve_show(
            client,
            rating_key="999",
            title=None,
            year=None,
            library=None,
            library_id=None,
        )
