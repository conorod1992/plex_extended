"""Safe regular-playlist mutations for Plex Extended."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .client import PlexExtendedClient, PlexExtendedError
from .library_lists import _serialize_playlist
from .user_context import PlexUserContext, resolve_user_context

_MAX_MUTATION_ITEMS = 50


def _rating_keys(value: Any) -> list[str]:
    """Return unique positive local Plex rating keys while preserving order."""
    if isinstance(value, str):
        values: Iterable[Any] = [value]
    else:
        values = value or []
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        key = str(raw).strip()
        if not key or not key.isdigit() or int(key) <= 0:
            raise PlexExtendedError(
                "Playlist mutations require positive numeric local Plex rating keys"
            )
        if key not in seen:
            seen.add(key)
            result.append(key)
    if not result:
        raise PlexExtendedError("Provide at least one media rating_key")
    if len(result) > _MAX_MUTATION_ITEMS:
        raise PlexExtendedError(
            f"Playlist mutations support at most {_MAX_MUTATION_ITEMS} media items at once"
        )
    return result


def _playlist_by_rating_key(server: Any, rating_key: Any) -> Any:
    """Resolve one playlist only by its stable rating key."""
    key = str(rating_key or "").strip()
    if not key or not key.isdigit() or int(key) <= 0:
        raise PlexExtendedError(
            "Provide the exact numeric playlist rating_key returned by list_playlists"
        )
    matches = [
        playlist
        for playlist in server.playlists()
        if str(getattr(playlist, "ratingKey", "")) == key
    ]
    if not matches:
        raise PlexExtendedError(f"Plex playlist rating key not found: {key}")
    if len(matches) > 1:
        raise PlexExtendedError(f"Plex returned duplicate playlist rating key {key}")
    return matches[0]


def _assert_regular_playlist(playlist: Any) -> None:
    """Reject smart/radio playlists and incomplete playlist metadata."""
    if bool(getattr(playlist, "smart", False)):
        raise PlexExtendedError("Smart Plex playlists cannot be edited item-by-item")
    if bool(getattr(playlist, "radio", False)):
        raise PlexExtendedError("Plex radio playlists cannot be edited item-by-item")
    playlist_type = str(getattr(playlist, "playlistType", "") or "")
    if playlist_type not in {"audio", "video", "photo"}:
        raise PlexExtendedError("Plex playlist type is unavailable or unsupported")


def _item_key(item: Any) -> str | None:
    """Return an item's local rating key."""
    value = getattr(item, "ratingKey", None)
    return str(value) if value is not None else None


def _playlist_keys(playlist: Any) -> list[str]:
    """Return playlist media keys in current order."""
    return [key for item in playlist.items() if (key := _item_key(item)) is not None]


def _fetch_media(server: Any, rating_keys: list[str]) -> list[Any]:
    """Fetch exact local media in one bounded Plex request and preserve caller order."""
    fetched = list(server.fetchItems([int(key) for key in rating_keys]))
    by_key = {
        key: item
        for item in fetched
        if (key := _item_key(item)) is not None
    }
    missing = [key for key in rating_keys if key not in by_key]
    if missing:
        raise PlexExtendedError(
            "Plex media rating key(s) not found or inaccessible: " + ", ".join(missing)
        )
    items = [by_key[key] for key in rating_keys]
    for item in items:
        if str(getattr(item, "listType", "") or "") not in {"audio", "video", "photo"}:
            raise PlexExtendedError(
                f"Plex item {getattr(item, 'ratingKey', '?')} cannot be placed in a playlist"
            )
    return items


def _assert_playlist_type(playlist: Any, items: list[Any]) -> None:
    """Ensure every item is compatible with the playlist's Plex list type."""
    expected = str(getattr(playlist, "playlistType", "") or "")
    wrong = [
        str(getattr(item, "ratingKey", "?"))
        for item in items
        if str(getattr(item, "listType", "") or "") != expected
    ]
    if wrong:
        raise PlexExtendedError(
            f"Playlist type '{expected}' cannot contain media rating key(s): "
            + ", ".join(wrong)
        )


def _response(
    context: PlexUserContext,
    playlist: Any,
    *,
    changed: bool,
    extra: dict[str, Any],
) -> dict[str, Any]:
    """Build a compact mutation response with current playlist state."""
    current_keys = _playlist_keys(playlist)
    result: dict[str, Any] = {
        "success": True,
        "changed": changed,
        "playlist": _serialize_playlist(playlist, include_summary=False),
        "item_count": len(current_keys),
        **extra,
    }
    result.update(context.response_fields())
    return result


def _create_playlist(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Create one regular playlist from exact local media rating keys."""
    context = resolve_user_context(client, criteria.get("user"), criteria.get("user_id"))
    server = context.server
    title = str(criteria.get("title") or "").strip()
    if not title:
        raise PlexExtendedError("Provide a non-empty playlist title")
    keys = _rating_keys(criteria.get("rating_keys"))

    exact = [
        playlist
        for playlist in server.playlists()
        if str(getattr(playlist, "title", "")).casefold() == title.casefold()
    ]
    if len(exact) > 1:
        found = ", ".join(str(getattr(item, "ratingKey", "?")) for item in exact)
        raise PlexExtendedError(
            f"Multiple Plex playlists are already named '{title}' (rating keys: {found}); "
            "choose a different title"
        )
    if exact:
        existing = exact[0]
        _assert_regular_playlist(existing)
        current = _playlist_keys(existing)
        if current == keys:
            return _response(
                context,
                existing,
                changed=False,
                extra={
                    "created": False,
                    "requested_rating_keys": keys,
                    "added_rating_keys": [],
                    "already_exists": True,
                },
            )
        raise PlexExtendedError(
            f"A Plex playlist named '{title}' already exists with rating_key "
            f"{getattr(existing, 'ratingKey', '?')} and different contents"
        )

    items = _fetch_media(server, keys)
    item_types = {str(getattr(item, "listType", "") or "") for item in items}
    if len(item_types) != 1:
        raise PlexExtendedError(
            "A regular Plex playlist cannot mix audio, video, and photo media"
        )

    playlist = server.createPlaylist(title, items=items)
    _assert_regular_playlist(playlist)
    playlist.reload()
    current = _playlist_keys(playlist)
    if current != keys:
        raise PlexExtendedError(
            "Plex created the playlist but did not confirm the requested item sequence"
        )
    return _response(
        context,
        playlist,
        changed=True,
        extra={
            "created": True,
            "requested_rating_keys": keys,
            "added_rating_keys": keys,
            "already_exists": False,
        },
    )


def _add_to_playlist(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Idempotently add exact local media items to a regular playlist."""
    context = resolve_user_context(client, criteria.get("user"), criteria.get("user_id"))
    playlist = _playlist_by_rating_key(context.server, criteria.get("playlist_rating_key"))
    _assert_regular_playlist(playlist)
    keys = _rating_keys(criteria.get("rating_keys"))

    current_set = set(_playlist_keys(playlist))
    to_add = [key for key in keys if key not in current_set]
    already = [key for key in keys if key in current_set]

    if to_add:
        items = _fetch_media(context.server, to_add)
        _assert_playlist_type(playlist, items)
        playlist.addItems(items)
        playlist.reload()

    confirmed = set(_playlist_keys(playlist))
    missing = [key for key in keys if key not in confirmed]
    if missing:
        raise PlexExtendedError(
            "Plex did not confirm added playlist item(s): " + ", ".join(missing)
        )
    return _response(
        context,
        playlist,
        changed=bool(to_add),
        extra={
            "requested_rating_keys": keys,
            "added_rating_keys": to_add,
            "already_present_rating_keys": already,
        },
    )


def _remove_from_playlist(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Idempotently remove all occurrences of exact media keys from a regular playlist."""
    context = resolve_user_context(client, criteria.get("user"), criteria.get("user_id"))
    playlist = _playlist_by_rating_key(context.server, criteria.get("playlist_rating_key"))
    _assert_regular_playlist(playlist)
    keys = _rating_keys(criteria.get("rating_keys"))

    removed: list[dict[str, Any]] = []
    absent: list[str] = []
    for key in keys:
        initial = [item for item in playlist.items() if _item_key(item) == key]
        if not initial:
            absent.append(key)
            continue

        occurrences = 0
        for _ in range(len(initial)):
            matching = [item for item in playlist.items() if _item_key(item) == key]
            if not matching:
                break
            before = len(matching)
            playlist.removeItems(matching[0])
            playlist.reload()
            after = sum(1 for item in playlist.items() if _item_key(item) == key)
            if after >= before:
                raise PlexExtendedError(
                    f"Plex did not confirm removed playlist item: {key}"
                )
            occurrences += before - after

        remaining_for_key = sum(
            1 for item in playlist.items() if _item_key(item) == key
        )
        if remaining_for_key:
            raise PlexExtendedError(
                f"Plex did not confirm removed playlist item: {key}"
            )
        removed.append({"rating_key": key, "occurrences": occurrences})

    remaining = set(_playlist_keys(playlist))
    failed = [key for key in keys if key in remaining]
    if failed:
        raise PlexExtendedError(
            "Plex did not confirm removed playlist item(s): " + ", ".join(failed)
        )
    return _response(
        context,
        playlist,
        changed=bool(removed),
        extra={
            "requested_rating_keys": keys,
            "removed": removed,
            "already_absent_rating_keys": absent,
        },
    )


async def async_create_playlist(
    client: PlexExtendedClient, criteria: dict[str, Any]
) -> dict[str, Any]:
    """Create a regular playlist through the client's executor lock."""
    return await client._async_run(_create_playlist, client, dict(criteria))


async def async_add_to_playlist(
    client: PlexExtendedClient, criteria: dict[str, Any]
) -> dict[str, Any]:
    """Add media to a playlist through the client's executor lock."""
    return await client._async_run(_add_to_playlist, client, dict(criteria))


async def async_remove_from_playlist(
    client: PlexExtendedClient, criteria: dict[str, Any]
) -> dict[str, Any]:
    """Remove media from a playlist through the client's executor lock."""
    return await client._async_run(_remove_from_playlist, client, dict(criteria))
