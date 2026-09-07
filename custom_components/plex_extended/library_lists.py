"""Collections, playlists, and Plex Watchlist queries for Plex Extended."""

from __future__ import annotations

from typing import Any

from plexapi.exceptions import Unauthorized

from .client import PlexExtendedClient, PlexExtendedError
from .const import DEFAULT_LIMIT
from .user_context import resolve_user_context

_COLLECTION_TYPES = {"movie", "show", "artist", "album"}
_PLAYLIST_TYPES = {"audio", "video", "photo"}
_WATCHLIST_FILTERS = {"all", "available", "released"}
_WATCHLIST_SORTS = {
    "watchlisted_at": "watchlistedAt",
    "title": "titleSort",
    "release_date": "originallyAvailableAt",
    "critic_rating": "rating",
}


def _iso(value: Any) -> str | None:
    """Convert a Plex date/datetime to a JSON-safe string."""
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)


def _compact(data: dict[str, Any]) -> dict[str, Any]:
    """Remove empty optional fields while retaining False/zero values."""
    return {
        key: value
        for key, value in data.items()
        if value is not None and value != "" and value != []
    }


def _serialize_collection(collection: Any, include_summary: bool) -> dict[str, Any]:
    """Serialize a Plex collection without exposing filesystem/token data."""
    data: dict[str, Any] = {
        "rating_key": str(getattr(collection, "ratingKey", "")) or None,
        "type": "collection",
        "title": getattr(collection, "title", None),
        "library": getattr(collection, "librarySectionTitle", None),
        "library_id": getattr(collection, "librarySectionID", None),
        "subtype": getattr(collection, "subtype", None),
        "smart": getattr(collection, "smart", None),
        "child_count": getattr(collection, "childCount", None),
        "min_year": getattr(collection, "minYear", None),
        "max_year": getattr(collection, "maxYear", None),
        "added_at": _iso(getattr(collection, "addedAt", None)),
        "updated_at": _iso(getattr(collection, "updatedAt", None)),
        "thumb": getattr(collection, "thumb", None),
    }
    if include_summary:
        data["summary"] = getattr(collection, "summary", None)
    return _compact(data)


def _serialize_playlist(playlist: Any, include_summary: bool) -> dict[str, Any]:
    """Serialize a Plex playlist."""
    data: dict[str, Any] = {
        "rating_key": str(getattr(playlist, "ratingKey", "")) or None,
        "type": "playlist",
        "title": getattr(playlist, "title", None),
        "playlist_type": getattr(playlist, "playlistType", None),
        "smart": getattr(playlist, "smart", None),
        "radio": getattr(playlist, "radio", None),
        "item_count": getattr(playlist, "leafCount", None),
        "duration_ms": getattr(playlist, "duration", None),
        "added_at": _iso(getattr(playlist, "addedAt", None)),
        "updated_at": _iso(getattr(playlist, "updatedAt", None)),
        "thumb": getattr(playlist, "thumb", None),
    }
    if include_summary:
        data["summary"] = getattr(playlist, "summary", None)
    return _compact(data)


def _collection_sections(client: PlexExtendedClient, server: Any, criteria: dict[str, Any]) -> list[Any]:
    """Return selected or accessible collection-capable sections."""
    selected = client._section(
        criteria.get("library"), criteria.get("library_id"), server
    )
    sections = [selected] if selected is not None else list(server.library.sections())
    return [
        section
        for section in sections
        if str(getattr(section, "type", "")) in {"movie", "show", "artist"}
    ]


def _resolve_collection(
    client: PlexExtendedClient,
    server: Any,
    criteria: dict[str, Any],
) -> Any:
    """Resolve a collection by stable rating key or unambiguous exact title."""
    rating_key = criteria.get("rating_key")
    selected = client._section(
        criteria.get("library"), criteria.get("library_id"), server
    )

    if rating_key:
        item = server.fetchItem(str(rating_key))
        if str(getattr(item, "type", "")) != "collection":
            raise PlexExtendedError(
                f"Plex rating key {rating_key} is not a collection"
            )
        if selected is not None and str(getattr(item, "librarySectionID", "")) != str(
            selected.key
        ):
            raise PlexExtendedError(
                f"Collection {rating_key} is not in library '{selected.title}'"
            )
        return item

    title = criteria.get("title")
    if not title:
        raise PlexExtendedError("Provide collection rating_key or title")

    matches: list[Any] = []
    wanted = str(title).casefold()
    for section in _collection_sections(client, server, criteria):
        for collection in section.collections():
            if str(getattr(collection, "title", "")).casefold() == wanted:
                matches.append(collection)

    if not matches:
        raise PlexExtendedError(f"Plex collection not found: {title}")
    if len(matches) > 1:
        choices = ", ".join(
            f"{item.title} (library {getattr(item, 'librarySectionTitle', '?')}, "
            f"rating_key {getattr(item, 'ratingKey', '?')})"
            for item in matches[:5]
        )
        raise PlexExtendedError(
            f"Multiple Plex collections are named '{title}'. Use rating_key or library_id: {choices}"
        )
    return matches[0]


def _list_collections(client: PlexExtendedClient, criteria: dict[str, Any]) -> dict[str, Any]:
    """List collections visible to the selected/default Plex user."""
    context = resolve_user_context(
        client, criteria.get("user"), criteria.get("user_id")
    )
    subtype = criteria.get("media_type")
    if subtype and subtype not in _COLLECTION_TYPES:
        raise PlexExtendedError(f"Unsupported collection media type: {subtype}")

    title_query = str(criteria.get("title") or "").casefold()
    max_results = client._normalize_limit(criteria.get("limit", DEFAULT_LIMIT))
    include_summary = bool(criteria.get("include_summary", True))

    collections: list[Any] = []
    for section in _collection_sections(client, context.server, criteria):
        for collection in section.collections():
            if subtype and str(getattr(collection, "subtype", "")) != subtype:
                continue
            if title_query and title_query not in str(getattr(collection, "title", "")).casefold():
                continue
            collections.append(collection)

    collections.sort(key=lambda item: str(getattr(item, "title", "")).casefold())
    collections = collections[:max_results]
    result: dict[str, Any] = {
        "success": True,
        "count": len(collections),
        "collections": [
            _serialize_collection(item, include_summary) for item in collections
        ],
    }
    result.update(context.response_fields())
    return result


async def async_list_collections(
    client: PlexExtendedClient, criteria: dict[str, Any]
) -> dict[str, Any]:
    """List collections through the client's executor lock."""
    return await client._async_run(_list_collections, client, dict(criteria))


def _collection_items(client: PlexExtendedClient, criteria: dict[str, Any]) -> dict[str, Any]:
    """Return items in one Plex collection."""
    context = resolve_user_context(
        client, criteria.get("user"), criteria.get("user_id")
    )
    collection = _resolve_collection(client, context.server, criteria)
    max_results = client._normalize_limit(criteria.get("limit", DEFAULT_LIMIT))
    include_summary = bool(criteria.get("include_summary", True))
    media_types = set(criteria.get("media_types") or [])

    items = list(collection.items())
    if media_types:
        items = [item for item in items if str(getattr(item, "type", "")) in media_types]
    items = items[:max_results]

    result: dict[str, Any] = {
        "success": True,
        "collection": _serialize_collection(collection, include_summary=False),
        "count": len(items),
        "results": [
            client._serialize_item(item, include_summary=include_summary) for item in items
        ],
    }
    result.update(context.response_fields())
    return result


async def async_collection_items(
    client: PlexExtendedClient, criteria: dict[str, Any]
) -> dict[str, Any]:
    """Return collection items through the client's executor lock."""
    return await client._async_run(_collection_items, client, dict(criteria))


def _resolve_playlist(server: Any, criteria: dict[str, Any]) -> Any:
    """Resolve a playlist by stable rating key or unambiguous exact title."""
    rating_key = criteria.get("rating_key")
    title = criteria.get("title")
    playlists = list(server.playlists())

    if rating_key:
        matches = [
            item
            for item in playlists
            if str(getattr(item, "ratingKey", "")) == str(rating_key)
        ]
        if not matches:
            raise PlexExtendedError(f"Plex playlist rating key not found: {rating_key}")
        return matches[0]

    if not title:
        raise PlexExtendedError("Provide playlist rating_key or title")
    wanted = str(title).casefold()
    matches = [
        item
        for item in playlists
        if str(getattr(item, "title", "")).casefold() == wanted
    ]
    if not matches:
        raise PlexExtendedError(f"Plex playlist not found: {title}")
    if len(matches) > 1:
        keys = ", ".join(str(getattr(item, "ratingKey", "?")) for item in matches)
        raise PlexExtendedError(
            f"Multiple Plex playlists are named '{title}'. Use rating_key ({keys})"
        )
    return matches[0]


def _list_playlists(client: PlexExtendedClient, criteria: dict[str, Any]) -> dict[str, Any]:
    """List playlists visible to the selected/default Plex user."""
    context = resolve_user_context(
        client, criteria.get("user"), criteria.get("user_id")
    )
    playlist_type = criteria.get("playlist_type")
    if playlist_type and playlist_type not in _PLAYLIST_TYPES:
        raise PlexExtendedError(f"Unsupported playlist type: {playlist_type}")
    max_results = client._normalize_limit(criteria.get("limit", DEFAULT_LIMIT))
    include_summary = bool(criteria.get("include_summary", True))
    title = criteria.get("title") or None

    playlists = list(
        context.server.playlists(
            playlistType=playlist_type or None,
            title=title,
            sort="titleSort:asc",
        )
    )[:max_results]
    result: dict[str, Any] = {
        "success": True,
        "count": len(playlists),
        "playlists": [
            _serialize_playlist(item, include_summary) for item in playlists
        ],
    }
    result.update(context.response_fields())
    return result


async def async_list_playlists(
    client: PlexExtendedClient, criteria: dict[str, Any]
) -> dict[str, Any]:
    """List playlists through the client's executor lock."""
    return await client._async_run(_list_playlists, client, dict(criteria))


def _playlist_items(client: PlexExtendedClient, criteria: dict[str, Any]) -> dict[str, Any]:
    """Return items in one Plex playlist."""
    context = resolve_user_context(
        client, criteria.get("user"), criteria.get("user_id")
    )
    playlist = _resolve_playlist(context.server, criteria)
    max_results = client._normalize_limit(criteria.get("limit", DEFAULT_LIMIT))
    include_summary = bool(criteria.get("include_summary", True))
    media_types = set(criteria.get("media_types") or [])

    items = list(playlist.items())
    if media_types:
        items = [item for item in items if str(getattr(item, "type", "")) in media_types]
    items = items[:max_results]
    result: dict[str, Any] = {
        "success": True,
        "playlist": _serialize_playlist(playlist, include_summary=False),
        "count": len(items),
        "results": [
            client._serialize_item(item, include_summary=include_summary) for item in items
        ],
    }
    result.update(context.response_fields())
    return result


async def async_playlist_items(
    client: PlexExtendedClient, criteria: dict[str, Any]
) -> dict[str, Any]:
    """Return playlist items through the client's executor lock."""
    return await client._async_run(_playlist_items, client, dict(criteria))


def _serialize_watchlist_item(
    client: PlexExtendedClient,
    server: Any,
    item: Any,
    *,
    include_summary: bool,
    match_local: bool,
) -> dict[str, Any]:
    """Serialize online Watchlist metadata and optional local-library matches."""
    data: dict[str, Any] = {
        "type": getattr(item, "type", None),
        "title": getattr(item, "title", None),
        "year": getattr(item, "year", None),
        "guid": getattr(item, "guid", None),
        "watchlisted_at": _iso(getattr(item, "watchlistedAt", None)),
        "originally_available_at": _iso(getattr(item, "originallyAvailableAt", None)),
        "content_rating": getattr(item, "contentRating", None),
        "rating": getattr(item, "rating", None),
        "audience_rating": getattr(item, "audienceRating", None),
        "thumb": getattr(item, "thumb", None),
    }
    if include_summary:
        data["summary"] = getattr(item, "summary", None)

    if match_local:
        guid = getattr(item, "guid", None)
        item_type = getattr(item, "type", None)
        matches: list[Any] = []
        if guid and item_type in {"movie", "show"}:
            matches = list(server.library.search(guid=guid, libtype=item_type))
        local = [
            client._serialize_item(match, include_summary=False) for match in matches
        ]
        data["on_server"] = bool(local)
        data["local_match_count"] = len(local)
        if len(local) == 1:
            data["local_rating_key"] = local[0].get("rating_key")
            data["local_library"] = local[0].get("library")
            data["local_library_id"] = local[0].get("library_id")
        elif local:
            data["local_matches"] = local

    return _compact(data)


def _watchlist(client: PlexExtendedClient, criteria: dict[str, Any]) -> dict[str, Any]:
    """Return the configured Plex account's plex.tv Watchlist."""
    server = client._require_server()
    filter_name = str(criteria.get("filter", "all"))
    if filter_name not in _WATCHLIST_FILTERS:
        raise PlexExtendedError(f"Unsupported Watchlist filter: {filter_name}")

    media_type = criteria.get("media_type")
    if media_type not in (None, "movie", "show"):
        raise PlexExtendedError(f"Unsupported Watchlist media type: {media_type}")

    sort_by = str(criteria.get("sort_by", "watchlisted_at"))
    sort_field = _WATCHLIST_SORTS.get(sort_by)
    if sort_field is None:
        raise PlexExtendedError(f"Unsupported Watchlist sort field: {sort_by}")
    sort_order = str(criteria.get("sort_order", "desc"))
    if sort_order not in {"asc", "desc"}:
        raise PlexExtendedError(f"Unsupported Watchlist sort order: {sort_order}")

    max_results = client._normalize_limit(criteria.get("limit", DEFAULT_LIMIT))
    include_summary = bool(criteria.get("include_summary", True))
    match_local = bool(criteria.get("match_local", True))

    try:
        account = server.myPlexAccount()
        items = account.watchlist(
            filter=None if filter_name == "all" else filter_name,
            sort=f"{sort_field}:{sort_order}",
            libtype=media_type,
            maxresults=max_results,
        )
    except Unauthorized as err:
        raise PlexExtendedError(
            "Plex Watchlist requires a token that can authenticate with plex.tv. "
            "Reconnect Plex Extended using Connect with Plex."
        ) from err

    results = [
        _serialize_watchlist_item(
            client,
            server,
            item,
            include_summary=include_summary,
            match_local=match_local,
        )
        for item in list(items)[:max_results]
    ]
    return {
        "success": True,
        "count": len(results),
        "account_scope": "configured_plex_account",
        "match_local": match_local,
        "results": results,
    }


async def async_watchlist(
    client: PlexExtendedClient, criteria: dict[str, Any]
) -> dict[str, Any]:
    """Return Plex Watchlist through the client's executor lock."""
    return await client._async_run(_watchlist, client, dict(criteria))
