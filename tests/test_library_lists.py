"""Tests for Plex Extended collections, playlists, and Watchlist queries."""

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


def _load(name: str, filename: str) -> ModuleType:
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

const = _load("const", "const.py")
client_module = _load("client", "client.py")
_load("user_context", "user_context.py")
lists_module = _load("library_lists", "library_lists.py")

PlexExtendedClient = client_module.PlexExtendedClient
PlexExtendedError = client_module.PlexExtendedError
_list_collections = lists_module._list_collections
_collection_items = lists_module._collection_items
_list_playlists = lists_module._list_playlists
_playlist_items = lists_module._playlist_items
_watchlist = lists_module._watchlist


def _media(title: str, media_type: str = "movie", rating_key: str | None = None):
    return SimpleNamespace(
        title=title,
        type=media_type,
        ratingKey=rating_key or title,
        librarySectionID=1,
        librarySectionTitle="Movies",
        viewCount=0,
    )


class FakeCollection:
    def __init__(self, title: str, rating_key: str, items=None, subtype="movie", library_id=1, library="Movies"):
        self.title = title
        self.ratingKey = rating_key
        self.type = "collection"
        self.subtype = subtype
        self.librarySectionID = library_id
        self.librarySectionTitle = library
        self.smart = False
        self.childCount = len(items or [])
        self._items = list(items or [])

    def items(self):
        return list(self._items)


class FakeSection:
    def __init__(self, key: int, title: str, collections=None, section_type="movie"):
        self.key = key
        self.title = title
        self.type = section_type
        self._collections = list(collections or [])

    def collections(self):
        return list(self._collections)


class FakePlaylist:
    def __init__(self, title: str, rating_key: str, items=None, playlist_type="video"):
        self.title = title
        self.ratingKey = rating_key
        self.type = "playlist"
        self.playlistType = playlist_type
        self.smart = False
        self.radio = False
        self.leafCount = len(items or [])
        self._items = list(items or [])

    def items(self):
        return list(self._items)


class FakeLibrary:
    def __init__(self, sections=None):
        self._sections = list(sections or [])
        self.local_matches = {}
        self.search_calls = []

    def sections(self):
        return list(self._sections)

    def search(self, guid=None, libtype=None):
        self.search_calls.append((guid, libtype))
        return list(self.local_matches.get((guid, libtype), []))


class FakeAccount:
    def __init__(self, items=None):
        self.items = list(items or [])
        self.calls = []

    def watchlist(self, **kwargs):
        self.calls.append(kwargs)
        return self.items[: kwargs.get("maxresults")]


class FakeServer:
    def __init__(self, sections=None, playlists=None, account=None, accounts=None):
        self.library = FakeLibrary(sections)
        self._playlists = list(playlists or [])
        self._account = account or FakeAccount()
        self._accounts = list(accounts or [])
        self.switched = {}
        self.switch_calls = []

    def playlists(self, playlistType=None, title=None, sort=None):
        values = list(self._playlists)
        if playlistType:
            values = [item for item in values if item.playlistType == playlistType]
        if title:
            wanted = title.casefold()
            values = [item for item in values if wanted in item.title.casefold()]
        return values

    def fetchItem(self, rating_key):
        for section in self.library.sections():
            for collection in section.collections():
                if str(collection.ratingKey) == str(rating_key):
                    return collection
        raise RuntimeError("not found")

    def myPlexAccount(self):
        return self._account

    def systemAccounts(self):
        return list(self._accounts)

    def switchUser(self, name):
        self.switch_calls.append(name)
        return self.switched[name]


def _client(server: FakeServer, default_user_id: str | None = None) -> PlexExtendedClient:
    client = object.__new__(PlexExtendedClient)
    client._server = server
    options = {}
    if default_user_id is not None:
        options[const.CONF_DEFAULT_USER_ID] = default_user_id
    client.entry = SimpleNamespace(options=options)
    return client


def test_list_collections_uses_selected_user_context_and_filters() -> None:
    owner = FakeServer(accounts=[SimpleNamespace(id=7, name="Conor")])
    selected = FakeServer(
        sections=[
            FakeSection(1, "Movies", [
                FakeCollection("Bond", "10"),
                FakeCollection("Christmas", "11"),
            ])
        ]
    )
    owner.switched["Conor"] = selected
    client = _client(owner, "7")

    result = _list_collections(client, {"title": "christ", "include_summary": False})

    assert [item["title"] for item in result["collections"]] == ["Christmas"]
    assert result["user"] == "Conor"
    assert owner.switch_calls == ["Conor"]


def test_collection_title_ambiguity_requires_stable_selector() -> None:
    first = FakeCollection("Favorites", "10", library_id=1, library="Movies")
    second = FakeCollection("Favorites", "20", library_id=2, library="TV Shows", subtype="show")
    server = FakeServer(
        sections=[
            FakeSection(1, "Movies", [first]),
            FakeSection(2, "TV Shows", [second], section_type="show"),
        ]
    )
    client = _client(server)

    with pytest.raises(PlexExtendedError, match="Multiple Plex collections"):
        _collection_items(client, {"title": "Favorites", "limit": 10})


def test_collection_items_by_rating_key_return_compact_media() -> None:
    collection = FakeCollection(
        "Bond",
        "10",
        [_media("Dr. No", rating_key="101"), _media("Goldfinger", rating_key="102")],
    )
    client = _client(FakeServer(sections=[FakeSection(1, "Movies", [collection])]))

    result = _collection_items(
        client,
        {"rating_key": "10", "limit": 1, "include_summary": False},
    )

    assert result["collection"]["rating_key"] == "10"
    assert result["count"] == 1
    assert result["results"][0]["title"] == "Dr. No"


def test_list_playlists_uses_default_user_server() -> None:
    owner = FakeServer(accounts=[SimpleNamespace(id=7, name="Conor")])
    selected = FakeServer(
        playlists=[
            FakePlaylist("Christmas", "30", playlist_type="audio"),
            FakePlaylist("Movies", "31", playlist_type="video"),
        ]
    )
    owner.switched["Conor"] = selected
    client = _client(owner, "7")

    result = _list_playlists(
        client,
        {"playlist_type": "video", "include_summary": False},
    )

    assert [item["title"] for item in result["playlists"]] == ["Movies"]
    assert result["user_id"] == 7


def test_playlist_items_can_filter_media_types() -> None:
    playlist = FakePlaylist(
        "Mixed",
        "31",
        [_media("Alien", "movie"), _media("Pilot", "episode")],
    )
    client = _client(FakeServer(playlists=[playlist]))

    result = _playlist_items(
        client,
        {"title": "Mixed", "media_types": ["movie"], "include_summary": False},
    )

    assert result["playlist"]["rating_key"] == "31"
    assert [item["title"] for item in result["results"]] == ["Alien"]


def test_watchlist_is_account_scoped_and_matches_local_guid() -> None:
    online = SimpleNamespace(
        title="Alien",
        type="movie",
        year=1979,
        guid="plex://movie/alien",
        watchlistedAt=None,
    )
    account = FakeAccount([online])
    owner = FakeServer(
        account=account,
        accounts=[SimpleNamespace(id=7, name="Conor")],
    )
    owner.switched["Conor"] = FakeServer()
    owner.library.local_matches[("plex://movie/alien", "movie")] = [
        _media("Alien", "movie", "1234")
    ]
    client = _client(owner, "7")

    result = _watchlist(client, {"limit": 10, "match_local": True, "include_summary": False})

    assert owner.switch_calls == []
    assert result["account_scope"] == "configured_plex_account"
    assert result["results"][0]["on_server"] is True
    assert result["results"][0]["local_rating_key"] == "1234"
    assert owner.library.search_calls == [("plex://movie/alien", "movie")]


def test_watchlist_passes_filter_sort_and_media_type_to_plex() -> None:
    account = FakeAccount([])
    client = _client(FakeServer(account=account))

    _watchlist(
        client,
        {
            "filter": "released",
            "media_type": "movie",
            "sort_by": "critic_rating",
            "sort_order": "asc",
            "limit": 5,
            "match_local": False,
        },
    )

    assert account.calls == [
        {
            "filter": "released",
            "sort": "rating:asc",
            "libtype": "movie",
            "maxresults": 5,
        }
    ]
