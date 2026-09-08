"""Tests for exact-ID Plex playlist mutations."""

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


class FakeContext:
    def __init__(self, server, user=None, user_id=None):
        self.server = server
        self.user = user
        self.user_id = user_id

    def response_fields(self):
        return {
            "user_context": self.user or self.user_id or "configured_default",
        }


def resolve_user_context(client, user, user_id):
    client.context_calls.append((user, user_id))
    return FakeContext(client.server, user, user_id)


def serialize_playlist(playlist, include_summary=False):
    return {
        "rating_key": str(playlist.ratingKey),
        "title": playlist.title,
        "playlist_type": playlist.playlistType,
        "smart": playlist.smart,
        "radio": playlist.radio,
        "item_count": playlist.leafCount,
    }


_STUB_NAMES = (
    "custom_components.plex_extended.client",
    "custom_components.plex_extended.library_lists",
    "custom_components.plex_extended.user_context",
)
_saved_modules = {name: sys.modules.get(name) for name in _STUB_NAMES}

client_module = ModuleType(_STUB_NAMES[0])
client_module.PlexExtendedClient = PlexExtendedClient
client_module.PlexExtendedError = PlexExtendedError
sys.modules[client_module.__name__] = client_module

lists_module = ModuleType(_STUB_NAMES[1])
lists_module._serialize_playlist = serialize_playlist
sys.modules[lists_module.__name__] = lists_module

context_module = ModuleType(_STUB_NAMES[2])
context_module.PlexUserContext = FakeContext
context_module.resolve_user_context = resolve_user_context
sys.modules[context_module.__name__] = context_module

try:
    spec = importlib.util.spec_from_file_location(
        "custom_components.plex_extended.playlist_mutations",
        COMPONENT / "playlist_mutations.py",
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

_create_playlist = module._create_playlist
_add_to_playlist = module._add_to_playlist
_remove_from_playlist = module._remove_from_playlist
_rating_keys = module._rating_keys


class FakeMedia:
    def __init__(self, rating_key, *, list_type="video", title=None):
        self.ratingKey = int(rating_key)
        self.listType = list_type
        self.title = title or f"Item {rating_key}"


class FakePlaylistItem(FakeMedia):
    def __init__(self, rating_key, *, list_type="video", occurrence=1):
        super().__init__(rating_key, list_type=list_type)
        self.playlistItemID = f"{rating_key}-{occurrence}"


class FakePlaylist:
    def __init__(
        self,
        rating_key,
        title,
        items=(),
        *,
        playlist_type="video",
        smart=False,
        radio=False,
        stubborn_add=False,
        stubborn_remove=False,
    ):
        self.ratingKey = int(rating_key)
        self.title = title
        self.playlistType = playlist_type
        self.smart = smart
        self.radio = radio
        self._items = list(items)
        self.stubborn_add = stubborn_add
        self.stubborn_remove = stubborn_remove
        self.add_calls = []
        self.remove_calls = []
        self.reload_calls = 0
        self._sync_count()

    def _sync_count(self):
        self.leafCount = len(self._items)

    def items(self):
        return list(self._items)

    def addItems(self, items):
        values = list(items) if isinstance(items, (list, tuple)) else [items]
        self.add_calls.append([str(item.ratingKey) for item in values])
        if not self.stubborn_add:
            for item in values:
                occurrence = 1 + sum(
                    1 for existing in self._items if existing.ratingKey == item.ratingKey
                )
                self._items.append(
                    FakePlaylistItem(
                        item.ratingKey,
                        list_type=item.listType,
                        occurrence=occurrence,
                    )
                )
            self._sync_count()
        return self

    def removeItems(self, item):
        self.remove_calls.append(str(item.ratingKey))
        if not self.stubborn_remove:
            for index, existing in enumerate(self._items):
                if existing is item:
                    self._items.pop(index)
                    break
            self._sync_count()
        return self

    def reload(self):
        self.reload_calls += 1
        self._sync_count()
        return self


class FakeServer:
    def __init__(self, playlists=(), media=()):
        self._playlists = list(playlists)
        self.media = {str(item.ratingKey): item for item in media}
        self.fetch_calls = []
        self.create_calls = []
        self.next_playlist_key = 900
        self.stubborn_create = False

    def playlists(self):
        return list(self._playlists)

    def fetchItems(self, keys):
        self.fetch_calls.append(list(keys))
        return [self.media[str(key)] for key in keys if str(key) in self.media]

    def createPlaylist(self, title, items):
        values = list(items)
        self.create_calls.append((title, [str(item.ratingKey) for item in values]))
        playlist_items = [] if self.stubborn_create else [
            FakePlaylistItem(item.ratingKey, list_type=item.listType, occurrence=1)
            for item in values
        ]
        playlist = FakePlaylist(
            self.next_playlist_key,
            title,
            playlist_items,
            playlist_type=values[0].listType,
        )
        self.next_playlist_key += 1
        self._playlists.append(playlist)
        return playlist


class FakeClient:
    def __init__(self, server):
        self.server = server
        self.context_calls = []


def playlist_items(*keys, list_type="video"):
    occurrences = {}
    result = []
    for key in keys:
        occurrences[key] = occurrences.get(key, 0) + 1
        result.append(
            FakePlaylistItem(
                key,
                list_type=list_type,
                occurrence=occurrences[key],
            )
        )
    return result


def test_rating_keys_are_numeric_deduplicated_and_bounded() -> None:
    assert _rating_keys(["2", 1, "2"]) == ["2", "1"]
    with pytest.raises(PlexExtendedError, match="positive numeric"):
        _rating_keys(["abc"])
    with pytest.raises(PlexExtendedError, match="at most 50"):
        _rating_keys([str(value) for value in range(1, 52)])


def test_create_playlist_uses_selected_user_and_exact_media_ids() -> None:
    server = FakeServer(media=[FakeMedia(1), FakeMedia(2)])
    client = FakeClient(server)

    result = _create_playlist(
        client,
        {
            "title": "Weekend Movies",
            "rating_keys": ["1", "2"],
            "user_id": "7",
        },
    )

    assert client.context_calls == [(None, "7")]
    assert server.fetch_calls == [[1, 2]]
    assert server.create_calls == [("Weekend Movies", ["1", "2"])]
    assert result["changed"] is True
    assert result["created"] is True
    assert result["playlist"]["rating_key"] == "900"
    assert result["item_count"] == 2


def test_create_retry_is_idempotent_only_for_identical_existing_playlist() -> None:
    existing = FakePlaylist(20, "Weekend Movies", playlist_items(1, 2))
    server = FakeServer([existing], media=[FakeMedia(1), FakeMedia(2)])
    client = FakeClient(server)

    result = _create_playlist(
        client,
        {"title": "weekend movies", "rating_keys": ["1", "2"]},
    )

    assert result["changed"] is False
    assert result["already_exists"] is True
    assert server.create_calls == []
    assert server.fetch_calls == []

    with pytest.raises(PlexExtendedError, match="different contents"):
        _create_playlist(
            client,
            {"title": "Weekend Movies", "rating_keys": ["2", "1"]},
        )


def test_create_rejects_ambiguous_title_and_mixed_media_types() -> None:
    duplicate_a = FakePlaylist(20, "Mix", playlist_items(1))
    duplicate_b = FakePlaylist(21, "mix", playlist_items(2))
    client = FakeClient(FakeServer([duplicate_a, duplicate_b], media=[FakeMedia(3)]))
    with pytest.raises(PlexExtendedError, match="Multiple Plex playlists"):
        _create_playlist(client, {"title": "MIX", "rating_keys": ["3"]})

    server = FakeServer(media=[FakeMedia(1, list_type="video"), FakeMedia(2, list_type="audio")])
    with pytest.raises(PlexExtendedError, match="cannot mix"):
        _create_playlist(
            FakeClient(server),
            {"title": "Bad Mix", "rating_keys": ["1", "2"]},
        )
    assert server.create_calls == []


def test_create_rejects_missing_media_and_unconfirmed_create() -> None:
    server = FakeServer(media=[FakeMedia(1)])
    with pytest.raises(PlexExtendedError, match="not found or inaccessible: 2"):
        _create_playlist(
            FakeClient(server),
            {"title": "Missing", "rating_keys": ["1", "2"]},
        )

    stubborn = FakeServer(media=[FakeMedia(1)])
    stubborn.stubborn_create = True
    with pytest.raises(PlexExtendedError, match="did not confirm"):
        _create_playlist(
            FakeClient(stubborn),
            {"title": "Stubborn", "rating_keys": ["1"]},
        )


def test_add_is_idempotent_and_only_fetches_missing_items() -> None:
    playlist = FakePlaylist(30, "Queue", playlist_items(1))
    server = FakeServer([playlist], media=[FakeMedia(2), FakeMedia(3)])
    client = FakeClient(server)

    result = _add_to_playlist(
        client,
        {
            "playlist_rating_key": "30",
            "rating_keys": ["1", "2", "3"],
        },
    )

    assert server.fetch_calls == [[2, 3]]
    assert playlist.add_calls == [["2", "3"]]
    assert result["added_rating_keys"] == ["2", "3"]
    assert result["already_present_rating_keys"] == ["1"]
    assert result["changed"] is True

    again = _add_to_playlist(
        client,
        {"playlist_rating_key": "30", "rating_keys": ["1", "2", "3"]},
    )
    assert again["changed"] is False
    assert playlist.add_calls == [["2", "3"]]


def test_add_rejects_wrong_type_smart_radio_and_unconfirmed_write() -> None:
    audio = FakePlaylist(30, "Music", playlist_items(1, list_type="audio"), playlist_type="audio")
    with pytest.raises(PlexExtendedError, match="cannot contain"):
        _add_to_playlist(
            FakeClient(FakeServer([audio], media=[FakeMedia(2, list_type="video")])),
            {"playlist_rating_key": "30", "rating_keys": ["2"]},
        )

    for playlist in (
        FakePlaylist(31, "Smart", smart=True),
        FakePlaylist(32, "Radio", radio=True),
    ):
        with pytest.raises(PlexExtendedError, match="cannot be edited"):
            _add_to_playlist(
                FakeClient(FakeServer([playlist], media=[FakeMedia(2)])),
                {"playlist_rating_key": str(playlist.ratingKey), "rating_keys": ["2"]},
            )

    stubborn = FakePlaylist(33, "Stubborn", stubborn_add=True)
    with pytest.raises(PlexExtendedError, match="did not confirm added"):
        _add_to_playlist(
            FakeClient(FakeServer([stubborn], media=[FakeMedia(2)])),
            {"playlist_rating_key": "33", "rating_keys": ["2"]},
        )


def test_remove_removes_all_duplicate_occurrences_and_is_retry_safe() -> None:
    playlist = FakePlaylist(40, "Duplicates", playlist_items(1, 2, 2, 3))
    client = FakeClient(FakeServer([playlist]))

    result = _remove_from_playlist(
        client,
        {"playlist_rating_key": "40", "rating_keys": ["2", "9"]},
    )

    assert playlist.remove_calls == ["2", "2"]
    assert [str(item.ratingKey) for item in playlist.items()] == ["1", "3"]
    assert result["changed"] is True
    assert result["removed"] == [{"rating_key": "2", "occurrences": 2}]
    assert result["already_absent_rating_keys"] == ["9"]

    again = _remove_from_playlist(
        client,
        {"playlist_rating_key": "40", "rating_keys": ["2", "9"]},
    )
    assert again["changed"] is False
    assert playlist.remove_calls == ["2", "2"]


def test_remove_rejects_unknown_playlist_and_unconfirmed_write() -> None:
    with pytest.raises(PlexExtendedError, match="rating key not found"):
        _remove_from_playlist(
            FakeClient(FakeServer()),
            {"playlist_rating_key": "999", "rating_keys": ["1"]},
        )

    stubborn = FakePlaylist(50, "Stubborn", playlist_items(1), stubborn_remove=True)
    with pytest.raises(PlexExtendedError, match="did not confirm removed"):
        _remove_from_playlist(
            FakeClient(FakeServer([stubborn])),
            {"playlist_rating_key": "50", "rating_keys": ["1"]},
        )
