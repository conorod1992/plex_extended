"""Tests for Plex Discover search and exact Watchlist mutations."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"

custom_components = sys.modules.setdefault("custom_components", ModuleType("custom_components"))
custom_components.__path__ = [str(ROOT / "custom_components")]
package = sys.modules.setdefault(
    "custom_components.plex_extended", ModuleType("custom_components.plex_extended")
)
package.__path__ = [str(COMPONENT)]


class PlexExtendedError(Exception):
    pass


class PlexExtendedClient:
    pass


def serialize_online(client, server, item, *, include_summary, match_local):
    result = {
        "guid": item.guid,
        "type": item.type,
        "title": item.title,
        "year": item.year,
    }
    if include_summary:
        result["summary"] = getattr(item, "summary", None)
    if match_local:
        result["on_server"] = getattr(item, "on_server", False)
    return result


_STUB_NAMES = (
    "custom_components.plex_extended.client",
    "custom_components.plex_extended.const",
    "custom_components.plex_extended.library_lists",
)
_saved_modules = {name: sys.modules.get(name) for name in _STUB_NAMES}

client_module = ModuleType(_STUB_NAMES[0])
client_module.PlexExtendedClient = PlexExtendedClient
client_module.PlexExtendedError = PlexExtendedError
sys.modules[client_module.__name__] = client_module

const_module = ModuleType(_STUB_NAMES[1])
const_module.DEFAULT_LIMIT = 10
sys.modules[const_module.__name__] = const_module

library_lists = ModuleType(_STUB_NAMES[2])
library_lists._serialize_watchlist_item = serialize_online
sys.modules[library_lists.__name__] = library_lists

try:
    spec = importlib.util.spec_from_file_location(
        "custom_components.plex_extended.discover_watchlist",
        COMPONENT / "discover_watchlist.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
finally:
    for name, previous in _saved_modules.items():
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous

_discover_search = module._discover_search
_add_to_watchlist = module._add_to_watchlist
_remove_from_watchlist = module._remove_from_watchlist
_normalized_discover_guid = module._normalized_discover_guid


class FakeAccount:
    def __init__(self, results_by_query, *, stubborn=False):
        self.results_by_query = results_by_query
        self.watchlisted = set()
        self.stubborn = stubborn
        self.search_calls = []
        self.added = []
        self.removed = []

    def searchDiscover(self, query, limit=30, libtype=None, providers="discover"):
        self.search_calls.append((query, limit, libtype, providers))
        return list(self.results_by_query.get(query, []))[:limit]

    def onWatchlist(self, item):
        return item.guid in self.watchlisted

    def addToWatchlist(self, item):
        self.added.append(item.guid)
        if not self.stubborn:
            self.watchlisted.add(item.guid)

    def removeFromWatchlist(self, item):
        self.removed.append(item.guid)
        if not self.stubborn:
            self.watchlisted.discard(item.guid)


class FakeServer:
    def __init__(self, account):
        self.account = account

    def myPlexAccount(self):
        return self.account


class FakeClient:
    def __init__(self, account):
        self.server = FakeServer(account)

    def _require_server(self):
        return self.server

    @staticmethod
    def _normalize_limit(value):
        return max(1, min(int(value or 10), 50))


def item(guid, title="Example", media_type="movie", year=2026, on_server=False):
    return SimpleNamespace(
        guid=guid,
        title=title,
        type=media_type,
        year=year,
        summary="Summary",
        on_server=on_server,
    )


def test_discover_search_defaults_to_online_only_and_exact_provider() -> None:
    result_item = item("plex://movie/abc", title="Example")
    account = FakeAccount({"Example": [result_item]})

    result = _discover_search(FakeClient(account), {"query": "Example", "limit": 5})

    assert result["account_scope"] == "configured_plex_account"
    assert result["match_local"] is False
    assert result["count"] == 1
    assert "on_server" not in result["results"][0]
    assert account.search_calls == [("Example", 5, None, "discover")]


def test_discover_search_can_explicitly_match_local() -> None:
    result_item = item("plex://show/show1", media_type="show", on_server=True)
    account = FakeAccount({"Example": [result_item]})

    result = _discover_search(
        FakeClient(account),
        {"query": "Example", "media_type": "show", "match_local": True},
    )

    assert result["results"][0]["on_server"] is True
    assert account.search_calls[0][2] == "show"


def test_add_uses_guid_not_title_and_verifies() -> None:
    wrong = item("plex://movie/wrong", title="Collision")
    wanted = item("plex://movie/right", title="Collision")
    account = FakeAccount({"Collision": [wrong, wanted]})

    result = _add_to_watchlist(
        FakeClient(account),
        {"guid": wanted.guid, "title": "Collision"},
    )

    assert account.added == [wanted.guid]
    assert wrong.guid not in account.watchlisted
    assert result["changed"] is True
    assert result["on_watchlist"] is True
    assert result["guid"] == wanted.guid


def test_add_is_idempotent_when_already_watchlisted() -> None:
    wanted = item("plex://movie/right")
    account = FakeAccount({"Example": [wanted]})
    account.watchlisted.add(wanted.guid)

    result = _add_to_watchlist(
        FakeClient(account),
        {"guid": wanted.guid, "title": "Example"},
    )

    assert result["changed"] is False
    assert account.added == []


def test_remove_is_idempotent_and_exact() -> None:
    wanted = item("plex://show/right", media_type="show")
    account = FakeAccount({"Example": [wanted]})
    account.watchlisted.add(wanted.guid)

    result = _remove_from_watchlist(
        FakeClient(account),
        {"guid": wanted.guid, "title": "Example", "media_type": "show"},
    )

    assert account.removed == [wanted.guid]
    assert result["on_watchlist"] is False
    assert result["changed"] is True

    again = _remove_from_watchlist(
        FakeClient(account),
        {"guid": wanted.guid, "title": "Example"},
    )
    assert again["changed"] is False
    assert account.removed == [wanted.guid]


def test_stale_or_wrong_guid_never_falls_back_to_title() -> None:
    candidate = item("plex://movie/actual", title="Same Title")
    account = FakeAccount({"Same Title": [candidate]})

    with pytest.raises(PlexExtendedError, match="exact Discover guid"):
        _add_to_watchlist(
            FakeClient(account),
            {"guid": "plex://movie/not-actual", "title": "Same Title"},
        )

    assert account.added == []


def test_media_type_must_match_guid_type() -> None:
    candidate = item("plex://movie/actual")
    account = FakeAccount({"Example": [candidate]})

    with pytest.raises(PlexExtendedError, match="identifies a movie"):
        _add_to_watchlist(
            FakeClient(account),
            {"guid": candidate.guid, "title": "Example", "media_type": "show"},
        )


def test_write_failure_is_not_reported_as_success() -> None:
    wanted = item("plex://movie/right")
    account = FakeAccount({"Example": [wanted]}, stubborn=True)

    with pytest.raises(PlexExtendedError, match="did not confirm"):
        _add_to_watchlist(
            FakeClient(account),
            {"guid": wanted.guid, "title": "Example"},
        )

    assert account.added == [wanted.guid]


def test_rejects_non_discover_identifiers() -> None:
    for value in ("1234", "http://movie/abc", "plex://episode/abc", "plex://movie/"):
        with pytest.raises(PlexExtendedError, match="discover_search"):
            _normalized_discover_guid(value)
