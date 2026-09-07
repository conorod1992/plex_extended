"""Safe Plex viewing-state mutations."""

from __future__ import annotations

from typing import Any

from .client import PlexExtendedClient, PlexExtendedError
from .user_context import resolve_user_context

_CASCADE_TYPES = {"show", "season"}


def _played_state(item: Any) -> bool | None:
    """Return a Plex item's played state when the object exposes it."""
    for attribute in ("isWatched", "isPlayed"):
        try:
            if hasattr(item, attribute):
                return bool(getattr(item, attribute))
        except Exception:
            continue
    return None


def _set_watch_state(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
    *,
    watched: bool,
) -> dict[str, Any]:
    """Set one Plex item's watched state in the selected/default user context."""
    context = resolve_user_context(
        client,
        criteria.get("user"),
        criteria.get("user_id"),
    )
    rating_key = str(criteria["rating_key"])
    item = context.server.fetchItem(rating_key)

    method_name = "markWatched" if watched else "markUnwatched"
    method = getattr(item, method_name, None)
    if not callable(method):
        item_type = getattr(item, "type", None) or "unknown"
        raise PlexExtendedError(
            f"Plex item {rating_key} ({item_type}) does not support watched-state changes"
        )

    previous = _played_state(item)
    method()

    # Fetch a fresh object rather than trusting the mutated PlexAPI instance. This
    # verifies the server accepted the state change in the selected user's context.
    refreshed = context.server.fetchItem(rating_key)
    current = _played_state(refreshed)
    if current is None:
        raise PlexExtendedError(
            f"Plex did not return a verifiable watched state for item {rating_key}"
        )
    if current is not watched:
        state = "watched" if watched else "unwatched"
        raise PlexExtendedError(
            f"Plex did not confirm item {rating_key} as {state} after the update"
        )

    item_type = getattr(refreshed, "type", None) or getattr(item, "type", None)
    result: dict[str, Any] = {
        "success": True,
        "operation": "mark_watched" if watched else "mark_unwatched",
        "rating_key": rating_key,
        "type": item_type,
        "title": getattr(refreshed, "title", None) or getattr(item, "title", None),
        "previous_watched": previous,
        "watched": current,
        "scope": "item_and_children" if item_type in _CASCADE_TYPES else "item",
    }
    result.update(context.response_fields())
    return {key: value for key, value in result.items() if value is not None}


async def async_mark_watched(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Mark one Plex item watched for the selected/default user."""
    return await client._async_run(
        _set_watch_state,
        client,
        dict(criteria),
        watched=True,
    )


async def async_mark_unwatched(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Mark one Plex item unwatched for the selected/default user."""
    return await client._async_run(
        _set_watch_state,
        client,
        dict(criteria),
        watched=False,
    )
