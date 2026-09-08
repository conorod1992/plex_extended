"""Related-media queries for Plex Extended."""

from __future__ import annotations

from typing import Any

from plexapi.exceptions import NotFound, Unauthorized
from requests.exceptions import RequestException

from .client import PlexExtendedClient, PlexExtendedError
from .user_context import resolve_user_context

_SUPPORTED_SOURCE_TYPES = {"movie", "show"}


def _positive_rating_key(value: Any) -> str:
    """Normalize a local numeric Plex rating key."""
    text = str(value or "").strip()
    if not text.isdigit() or int(text) <= 0:
        raise PlexExtendedError("rating_key must be a positive local Plex numeric ID")
    return text


def _resolve_source(
    client: PlexExtendedClient,
    server: Any,
    criteria: dict[str, Any],
) -> Any:
    """Resolve and validate the exact local movie/show used as recommendation seed."""
    rating_key = _positive_rating_key(criteria.get("rating_key"))
    try:
        source = server.fetchItem(rating_key)
    except (Unauthorized, RequestException):
        # Let the client's executor wrapper translate transport/authentication
        # failures consistently and start Home Assistant reauthentication when
        # Plex rejects the configured token.
        raise
    except NotFound as err:
        raise PlexExtendedError(f"Plex media not found for rating key {rating_key}") from err
    except Exception as err:
        raise PlexExtendedError(
            f"Unable to load Plex media for rating key {rating_key}: {err}"
        ) from err

    media_type = str(getattr(source, "type", ""))
    if media_type not in _SUPPORTED_SOURCE_TYPES:
        raise PlexExtendedError(
            f"Plex rating key {rating_key} is '{media_type or 'unknown'}'; "
            "related_media supports movies and TV shows"
        )

    library = criteria.get("library")
    library_id = criteria.get("library_id")
    if library or library_id is not None:
        section = client._section(library, library_id, server)
        assert section is not None
        if str(getattr(source, "librarySectionID", "")) != str(section.key):
            raise PlexExtendedError(
                f"Plex rating key {rating_key} is not in library '{section.title}'"
            )
    return source


def _local_related_items(
    client: PlexExtendedClient,
    source: Any,
    items: list[Any],
    *,
    include_summary: bool,
    item_limit: int,
) -> tuple[list[dict[str, Any]], int]:
    """Return local movie/show recommendations, preserving hub order."""
    source_key = str(getattr(source, "ratingKey", ""))
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    eligible_count = 0

    for item in items:
        media_type = str(getattr(item, "type", ""))
        rating_key = getattr(item, "ratingKey", None)
        library_id = getattr(item, "librarySectionID", None)
        if media_type not in _SUPPORTED_SOURCE_TYPES:
            continue
        if rating_key is None or library_id is None:
            # The related endpoint can surface provider/online objects. Plex Extended
            # deliberately returns only concrete items from this local server.
            continue
        rating_key_text = str(rating_key)
        if rating_key_text == source_key:
            continue
        identity = (media_type, str(library_id), rating_key_text)
        if identity in seen:
            continue
        seen.add(identity)
        eligible_count += 1
        if len(results) >= item_limit:
            continue
        results.append(
            client._serialize_item(item, include_summary=include_summary)
        )

    return results, eligible_count


def _related_media(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return Plex-native related hubs for one exact local movie/show."""
    context = resolve_user_context(
        client,
        criteria.get("user"),
        criteria.get("user_id"),
    )
    source = _resolve_source(client, context.server, criteria)
    include_summary = bool(criteria.get("include_summary", True))
    hub_limit = max(1, min(int(criteria.get("hub_limit", 10)), 20))
    item_limit = max(1, min(int(criteria.get("item_limit", 10)), 20))

    try:
        plex_hubs = list(source.hubs())
    except (Unauthorized, RequestException):
        # Authentication and connection failures must remain visible to
        # PlexExtendedClient._async_run(), which owns their HA-facing behavior.
        raise
    except Exception as err:
        raise PlexExtendedError(
            f"Unable to load related media for '{getattr(source, 'title', 'Plex item')}'"
        ) from err

    hubs: list[dict[str, Any]] = []
    matched_hub_count = 0
    total_returned_items = 0
    for hub in plex_hubs:
        raw_items = list(getattr(hub, "items", None) or [])
        results, eligible_count = _local_related_items(
            client,
            source,
            raw_items,
            include_summary=include_summary,
            item_limit=item_limit,
        )
        if not results and eligible_count == 0:
            continue
        matched_hub_count += 1
        if len(hubs) >= hub_limit:
            continue

        declared_size = getattr(hub, "size", None)
        more = bool(getattr(hub, "more", False))
        hub_data: dict[str, Any] = {
            "title": getattr(hub, "title", None),
            "identifier": getattr(hub, "hubIdentifier", None),
            "context": getattr(hub, "context", None),
            "type": getattr(hub, "type", None),
            "declared_size": declared_size,
            "local_item_count_in_loaded_hub": eligible_count,
            "count": len(results),
            "more_available_from_plex": more,
            "results_truncated": more or eligible_count > len(results),
            "results": results,
        }
        hubs.append(
            {
                key: value
                for key, value in hub_data.items()
                if value not in (None, "", [])
                or key in {"more_available_from_plex", "results_truncated"}
            }
        )
        total_returned_items += len(results)

    result: dict[str, Any] = {
        "success": True,
        "source": client._serialize_item(source, include_summary=include_summary),
        "count": len(hubs),
        "matched_hub_count": matched_hub_count,
        "plex_hub_count": len(plex_hubs),
        "result_item_count": total_returned_items,
        "hubs_truncated": matched_hub_count > len(hubs),
        "hubs": hubs,
    }
    result.update(context.response_fields())
    return result


async def async_related_media(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return related media through the client's executor lock."""
    return await client._async_run(_related_media, client, dict(criteria))
