"""Tests for Plex Extended advanced library querying."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"


def _install_homeassistant_stubs() -> None:
    """Install the small Home Assistant surface imported by client.py."""
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
    """Load one integration module without running package __init__.py."""
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

custom_components = ModuleType("custom_components")
custom_components.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", custom_components)

package = ModuleType("custom_components.plex_extended")
package.__path__ = [str(COMPONENT)]
sys.modules.setdefault("custom_components.plex_extended", package)

const_module = _load_component_module("const", "const.py")
client_module = _load_component_module("client", "client.py")
_load_component_module("user_context", "user_context.py")
query_module = _load_component_module("library_query", "library_query.py")

PlexExtendedClient = client_module.PlexExtendedClient
PlexExtendedError = client_module.PlexExtendedError
_build_filters = query_module._build_filters
_build_sort = query_module._build_sort
_query_library = query_module._query_library


class FakeSection:
    """Minimal library section with a capturable search call."""

    def __init__(self, key: str, title: str, section_type: str) -> None:
        self.key = key
        self.title = title
        self.type = section_type
        self.search_results = []
        self.search_calls: list[dict[str, object]] = []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return self.search_results


class FakeLibrary:
    """Minimal Plex library container."""

    def __init__(self, sections: list[FakeSection]) -> None:
        self._sections = sections

    def sections(self) -> list[FakeSection]:
        return self._sections


class FakeServer:
    """Minimal server surface used by advanced query tests."""

    def __init__(self, sections: list[FakeSection], accounts=None) -> None:
        self.library = FakeLibrary(sections)
        self.fetches: list[str] = []
        self.accounts = accounts or []
        self.switched: dict[str, FakeServer] = {}
        self.switch_calls: list[str] = []

    def fetchItem(self, rating_key):
        self.fetches.append(str(rating_key))
        return SimpleNamespace(
            ratingKey=rating_key,
            type="movie",
            title="Fetched",
            librarySectionID=1,
            viewCount=0,
            media=[],
        )

    def systemAccounts(self):
        return list(self.accounts)

    def switchUser(self, name):
        self.switch_calls.append(str(name))
        return self.switched[str(name)]


def _client(
    server: FakeServer, default_user_id: str | None = None
) -> PlexExtendedClient:
    client = object.__new__(PlexExtendedClient)
    client._server = server
    options = {}
    if default_user_id is not None:
        options[const_module.CONF_DEFAULT_USER_ID] = default_user_id
    client.entry = SimpleNamespace(options=options)
    return client


def _item(title: str, rating_key: str = "1", view_count: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        ratingKey=rating_key,
        type="movie",
        title=title,
        librarySectionID=1,
        viewCount=view_count,
        roles=[SimpleNamespace(tag="Sigourney Weaver")],
        collections=[SimpleNamespace(tag="Alien Collection")],
    )


def test_build_filters_maps_typed_criteria() -> None:
    """Typed fields should become Plex-native filters where possible."""
    filters, post_filters = _build_filters(
        {
            "genres_all": ["Horror", "Science Fiction"],
            "actors": ["Sigourney Weaver"],
            "directors": ["Ridley Scott"],
            "collections": ["Alien Collection"],
            "content_ratings": ["R"],
            "studios": ["20th Century Fox"],
            "year_min": 1970,
            "year_max": 1979,
            "decade": 1970,
            "watched_state": "unwatched",
            "resolutions": ["4k", "1080"],
            "hdr": "hdr",
            "critic_rating_min": 7.5,
            "audience_rating_max": 9.0,
            "duration_min_minutes": 90,
            "duration_max_minutes": 120,
            "added_after": "30d",
            "last_viewed_before": "2026-01-01",
        }
    )

    assert filters["genre&"] == ["Horror", "Science Fiction"]
    assert filters["actor"] == ["Sigourney Weaver"]
    assert filters["director"] == ["Ridley Scott"]
    assert filters["collection"] == ["Alien Collection"]
    assert filters["contentRating"] == ["R"]
    assert filters["studio"] == ["20th Century Fox"]
    assert filters["year>>"] == 1969
    assert filters["year<<"] == 1980
    assert filters["decade"] == 1970
    assert filters["unwatched"] is True
    assert filters["resolution"] == ["4k", "1080"]
    assert filters["hdr"] is True
    assert filters["addedAt>>"] == "30d"
    assert filters["lastViewedAt<<"] == "2026-01-01"
    assert post_filters["rating__gte"] == 7.5
    assert post_filters["audienceRating__lte"] == 9.0
    assert post_filters["duration__gte"] == 5_400_000
    assert post_filters["duration__lte"] == 7_200_000


def test_richer_library_filters_split_native_and_technical_criteria() -> None:
    filters, post_filters = _build_filters(
        {
            "audio_languages": ["eng", "jpn"],
            "subtitle_languages": ["eng"],
            "labels": ["Keep"],
            "countries": ["Ireland"],
            "duplicates": True,
            "unmatched": False,
            "video_codecs": ["HEVC", "h264"],
            "audio_codecs": ["TRUEHD"],
            "containers": ["MKV"],
            "audio_channels": [6, 8],
        }
    )

    assert filters["audioLanguage"] == ["eng", "jpn"]
    assert filters["subtitleLanguage"] == ["eng"]
    assert filters["label"] == ["Keep"]
    assert filters["country"] == ["Ireland"]
    assert filters["duplicate"] is True
    assert filters["unmatched!"] is True
    assert post_filters["media__videoCodec__in"] == ["hevc", "h264"]
    assert post_filters["media__audioCodec__in"] == ["truehd"]
    assert post_filters["media__container__in"] == ["mkv"]
    assert post_filters["media__audioChannels__in"] == ["6", "8"]


def test_false_duplicate_filter_uses_plex_boolean_false_operator() -> None:
    filters, _ = _build_filters({"duplicates": False})
    assert filters == {"duplicate!": True}


def test_watched_and_sdr_filters_use_plex_false_operators() -> None:
    filters, _ = _build_filters({"watched_state": "watched", "hdr": "sdr"})
    assert filters["unwatched!"] is True
    assert filters["hdr!"] is True


def test_inverted_ranges_are_rejected() -> None:
    with pytest.raises(PlexExtendedError, match="Year minimum"):
        _build_filters({"year_min": 2020, "year_max": 2010})
    with pytest.raises(PlexExtendedError, match="Duration minimum"):
        _build_filters(
            {"duration_min_minutes": 120, "duration_max_minutes": 90}
        )


def test_sort_defaults_title_ascending_and_other_fields_descending() -> None:
    assert _build_sort({"sort_by": "title"}) == "titleSort:asc"
    assert _build_sort({"sort_by": "audience_rating"}) == "audienceRating:desc"
    assert _build_sort({"sort_by": "year", "sort_order": "asc"}) == "year:asc"


def test_query_auto_selects_single_compatible_library() -> None:
    movies = FakeSection("1", "Movies", "movie")
    television = FakeSection("2", "TV Shows", "show")
    movies.search_results = [_item("Alien")]
    client = _client(FakeServer([movies, television]))

    result = _query_library(
        client,
        {
            "media_type": "movie",
            "genres": ["Horror"],
            "watched_state": "unwatched",
            "limit": 5,
            "include_summary": False,
        },
    )

    assert result["library"] == "Movies"
    assert result["library_id"] == "1"
    assert result["results"][0]["actors"] == ["Sigourney Weaver"]
    assert result["results"][0]["collections"] == ["Alien Collection"]
    call = movies.search_calls[0]
    assert call["libtype"] == "movie"
    assert call["maxresults"] == 5
    assert call["filters"] == {"genre": ["Horror"], "unwatched": True}


def test_query_uses_default_users_library_and_watch_state() -> None:
    owner_movies = FakeSection("1", "Movies", "movie")
    user_movies = FakeSection("1", "Movies", "movie")
    user_movies.search_results = [_item("Alien", view_count=0)]
    accounts = [
        SimpleNamespace(id=1, name="Owner"),
        SimpleNamespace(id=7, name="Conor"),
    ]
    owner = FakeServer([owner_movies], accounts)
    conor = FakeServer([user_movies])
    owner.switched["Conor"] = conor
    client = _client(owner, "7")

    result = _query_library(
        client,
        {
            "media_type": "movie",
            "watched_state": "unwatched",
            "limit": 5,
            "include_summary": False,
        },
    )

    assert owner_movies.search_calls == []
    assert user_movies.search_calls[0]["filters"] == {"unwatched": True}
    assert result["user_id"] == 7
    assert result["user"] == "Conor"
    assert result["results"][0]["watched"] is False


def test_query_refuses_to_guess_between_multiple_compatible_libraries() -> None:
    client = _client(
        FakeServer(
            [
                FakeSection("1", "Movies", "movie"),
                FakeSection("3", "Kids Movies", "movie"),
            ]
        )
    )

    with pytest.raises(PlexExtendedError, match="Multiple Plex libraries"):
        _query_library(client, {"media_type": "movie", "limit": 10})


def test_query_explicit_library_must_match_media_type() -> None:
    television = FakeSection("2", "TV Shows", "show")
    client = _client(FakeServer([television]))

    with pytest.raises(PlexExtendedError, match="cannot be queried for 'movie'"):
        _query_library(
            client,
            {"media_type": "movie", "library_id": "2", "limit": 10},
        )
