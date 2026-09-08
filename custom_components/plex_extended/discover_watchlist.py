"""Plex Discover search and safe account Watchlist mutations."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .client import PlexExtendedClient, PlexExtendedError
from .const import DEFAULT_LIMIT
from .library_lists import _serialize_watchlist_item

_DISCOVER_TYPES = {"movie", "show"}


def _normalized_discover_guid(value: Any) -> tuple[str, str]:
    """Validate and normalize a Plex Discover movie/show GUID."""
    guid = str(value or "").strip()
    parsed = urlparse(guid)
    media_type = parsed.netloc.casefold()
    identifier = parsed.path.strip("/")
    if parsed.scheme.casefold() != "plex" or media_type not in _DISCOVER_TYPES or not identifier:
        raise PlexExtendedError(
            "Discover guid must be a plex://movie/... or plex://show/... value returned by discover_search"
        )
    return guid, media_type


def _discover_account(client: PlexExtendedClient) -> tuple[Any, Any]:
    """Return the local server and the configured plex.tv account."""
    server = client._require_server()
    account = server.myPlexAccount()
    return server, account


def _discover_search(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Search Plex Discover for movies/shows outside the local library."""
    server, account = _discover_account(client)
    query = str(criteria.get("query") or "").strip()
    if not query:
        raise PlexExtendedError("Provide a Discover search query")

    media_type = criteria.get("media_type")
    if media_type not in (None, "movie", "show"):
        raise PlexExtendedError(f"Unsupported Discover media type: {media_type}")

    max_results = client._normalize_limit(criteria.get("limit", DEFAULT_LIMIT))
    include_summary = bool(criteria.get("include_summary", True))
    match_local = bool(criteria.get("match_local", False))

    items = list(
        account.searchDiscover(
            query,
            limit=max_results,
            libtype=media_type,
            providers="discover",
        )
    )[:max_results]
    return {
        "success": True,
        "count": len(items),
        "account_scope": "configured_plex_account",
        "match_local": match_local,
        "results": [
            _serialize_watchlist_item(
                client,
                server,
                item,
                include_summary=include_summary,
                match_local=match_local,
            )
            for item in items
        ],
    }


async def async_discover_search(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Search Discover through the client's executor lock."""
    return await client._async_run(_discover_search, client, dict(criteria))


def _resolve_discover_item(
    account: Any,
    *,
    guid: str,
    title: str,
    media_type: str | None,
) -> Any:
    """Resolve a Discover object by re-searching then requiring an exact GUID match."""
    normalized_guid, guid_type = _normalized_discover_guid(guid)
    if media_type is not None and media_type not in _DISCOVER_TYPES:
        raise PlexExtendedError(f"Unsupported Discover media type: {media_type}")
    if media_type is not None and media_type != guid_type:
        raise PlexExtendedError(
            f"Discover guid identifies a {guid_type}, not a {media_type}"
        )

    lookup_title = str(title or "").strip()
    if not lookup_title:
        raise PlexExtendedError(
            "Provide the title returned by discover_search together with the exact Discover guid"
        )

    candidates = list(
        account.searchDiscover(
            lookup_title,
            limit=50,
            libtype=guid_type,
            providers="discover",
        )
    )
    matches = [
        item
        for item in candidates
        if str(getattr(item, "guid", "")) == normalized_guid
    ]
    if not matches:
        raise PlexExtendedError(
            "The exact Discover guid could not be resolved from Plex. Run discover_search again and use the guid/title from that result."
        )
    return matches[0]


def _set_watchlist_state(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
    *,
    watched: bool,
) -> dict[str, Any]:
    """Set account Watchlist membership for one exact Discover item and verify it."""
    server, account = _discover_account(client)
    guid, guid_type = _normalized_discover_guid(criteria.get("guid"))
    media_type = criteria.get("media_type")
    item = _resolve_discover_item(
        account,
        guid=guid,
        title=str(criteria.get("title") or ""),
        media_type=str(media_type) if media_type is not None else None,
    )

    before = bool(account.onWatchlist(item))
    changed = before != watched
    if changed:
        if watched:
            account.addToWatchlist(item)
        else:
            account.removeFromWatchlist(item)

    after = bool(account.onWatchlist(item))
    if after != watched:
        action = "add" if watched else "remove"
        raise PlexExtendedError(
            f"Plex did not confirm the requested Watchlist {action} operation"
        )

    return {
        "success": True,
        "changed": changed,
        "account_scope": "configured_plex_account",
        "on_watchlist": after,
        "media": _serialize_watchlist_item(
            client,
            server,
            item,
            include_summary=False,
            match_local=False,
        ),
        "guid": guid,
        "media_type": guid_type,
    }


def _add_to_watchlist(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    return _set_watchlist_state(client, criteria, watched=True)


def _remove_from_watchlist(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    return _set_watchlist_state(client, criteria, watched=False)


async def async_add_to_watchlist(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Add one exact Discover item to the account Watchlist."""
    return await client._async_run(_add_to_watchlist, client, dict(criteria))


async def async_remove_from_watchlist(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Remove one exact Discover item from the account Watchlist."""
    return await client._async_run(_remove_from_watchlist, client, dict(criteria))
