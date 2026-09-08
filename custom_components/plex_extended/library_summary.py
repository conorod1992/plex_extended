"""Aggregate Plex library summaries for Plex Extended."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from .client import PlexExtendedClient, PlexExtendedError
from .const import DEFAULT_FACET_LIMIT, LIBRARY_SUMMARY_FACETS, MAX_FACET_LIMIT
from .library_query import _build_filters, _resolve_query_section
from .user_context import PlexUserContext, resolve_user_context

_DETAIL_BATCH_SIZE = 100
_HYDRATED_FACETS = {"genre", "resolution", "collection"}


def _criterion_values(value: Any) -> list[str]:
    """Return deduplicated non-empty strings while preserving order."""
    if value is None:
        return []
    values: Iterable[Any] = [value] if isinstance(value, str) else value
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _normalized_facet_limit(value: Any) -> int:
    """Clamp facet output to a safe, predictable range."""
    if value is None:
        return DEFAULT_FACET_LIMIT
    return max(1, min(int(value), MAX_FACET_LIMIT))


def _server_filtered_count(
    section: Any,
    media_type: str,
    title: str | None,
    filters: dict[str, Any],
) -> int | None:
    """Return Plex's filtered total without downloading all matching items.

    PlexAPI exposes the validated search-key builder but not a public filtered-count
    helper. Plex Media Server returns `totalSize` on the same search endpoint, so a
    one-item container query can obtain an exact server-side count efficiently. The
    integration pins PlexAPI, and this private helper use is isolated here so a future
    dependency change has one compatibility point.
    """
    key = section._buildSearchKey(
        title=title or None,
        libtype=media_type,
        filters=filters or None,
        includeGuids=False,
    )
    data = section._server.query(
        key,
        headers={
            "X-Plex-Container-Start": "0",
            "X-Plex-Container-Size": "1",
        },
    )
    total = data.attrib.get("totalSize")
    if total is None:
        return None
    try:
        return int(total)
    except (TypeError, ValueError):
        return None


def _matching_items(
    section: Any,
    media_type: str,
    title: str | None,
    filters: dict[str, Any],
    post_filters: dict[str, Any],
) -> list[Any]:
    """Materialize the complete exact result set when aggregation requires it."""
    return list(
        section.search(
            title=title or None,
            libtype=media_type,
            filters=filters or None,
            includeGuids=False,
            **post_filters,
        )
    )


def _rating_key(item: Any) -> str | None:
    """Return an item's stable local rating key without triggering a reload."""
    value = object.__getattribute__(item, "__dict__").get("ratingKey")
    return str(value) if value is not None else None


def _hydrate_items(server: Any, items: list[Any]) -> list[Any]:
    """Fetch full item metadata in batches for tag/technical facets.

    Library search rows are partial Plex objects. Accessing a missing `genres` or
    `media` property one item at a time can cause an N+1 reload storm, so exact facets
    that need child metadata are hydrated through Plex's multi-rating-key endpoint in
    bounded batches.
    """
    numeric_keys: list[int] = []
    original_by_key: dict[str, Any] = {}
    for item in items:
        key = _rating_key(item)
        if key is None:
            continue
        original_by_key[key] = item
        if key.isdigit():
            numeric_keys.append(int(key))

    hydrated_by_key: dict[str, Any] = {}
    for start in range(0, len(numeric_keys), _DETAIL_BATCH_SIZE):
        chunk = numeric_keys[start : start + _DETAIL_BATCH_SIZE]
        for item in server.fetchItems(chunk):
            key = _rating_key(item)
            if key is not None:
                hydrated_by_key[key] = item

    result: list[Any] = []
    for item in items:
        key = _rating_key(item)
        result.append(hydrated_by_key.get(key, item) if key is not None else item)
    return result


def _tag_values(item: Any, attribute: str) -> list[str]:
    """Return compact tag/title values from a fully hydrated Plex item."""
    values = getattr(item, attribute, None) or []
    result: list[str] = []
    for value in values:
        name = getattr(value, "tag", None) or getattr(value, "title", None)
        if name:
            result.append(str(name))
    return result


def _resolution_values(item: Any) -> list[str]:
    """Return unique media resolutions for an item."""
    values: list[str] = []
    for media in getattr(item, "media", None) or []:
        resolution = getattr(media, "videoResolution", None)
        if resolution:
            values.append(str(resolution))
    return values


def _watched_state(item: Any) -> str | None:
    """Classify one Plex item into watched/in-progress/unwatched when meaningful."""
    data = object.__getattribute__(item, "__dict__")

    try:
        played = getattr(item, "isPlayed")
    except Exception:
        played = None
    if played is True:
        return "watched"

    view_count = data.get("viewCount")
    if view_count:
        return "watched"

    viewed_leaf_count = data.get("viewedLeafCount")
    leaf_count = data.get("leafCount")
    if viewed_leaf_count is not None and leaf_count is not None:
        try:
            viewed = int(viewed_leaf_count)
            total = int(leaf_count)
        except (TypeError, ValueError):
            pass
        else:
            if total > 0 and viewed >= total:
                return "watched"
            if viewed > 0:
                return "in_progress"
            return "unwatched"

    view_offset = data.get("viewOffset")
    if view_offset:
        return "in_progress"

    if view_count is not None or view_offset is not None or played is False:
        return "unwatched"
    return None


def _facet_values(item: Any, facet: str) -> list[Any]:
    """Return one item's membership values for a supported summary facet."""
    if facet == "genre":
        return _tag_values(item, "genres")
    if facet == "collection":
        return _tag_values(item, "collections")
    if facet == "resolution":
        return _resolution_values(item)
    if facet == "watched_state":
        value = _watched_state(item)
        return [value] if value is not None else []

    data = object.__getattribute__(item, "__dict__")
    if facet == "year":
        value = data.get("year")
        return [int(value)] if value is not None else []
    if facet == "decade":
        value = data.get("year")
        if value is None:
            return []
        year = int(value)
        return [f"{(year // 10) * 10}s"]
    if facet == "content_rating":
        value = data.get("contentRating")
        return [str(value)] if value else []
    if facet == "studio":
        value = data.get("studio")
        return [str(value)] if value else []
    raise PlexExtendedError(f"Unsupported library-summary facet: {facet}")


def _facet_summary(items: list[Any], facet: str, limit: int) -> dict[str, Any]:
    """Return a compact count distribution for one facet."""
    counts: Counter[Any] = Counter()
    labels: dict[Any, Any] = {}
    missing_items = 0

    for item in items:
        raw_values = _facet_values(item, facet)
        if not raw_values:
            missing_items += 1
            continue

        seen_item_values: set[Any] = set()
        for value in raw_values:
            if isinstance(value, str):
                identity: Any = ("str", value.casefold())
            else:
                identity = ("value", value)
            if identity in seen_item_values:
                continue
            seen_item_values.add(identity)
            counts[identity] += 1
            labels.setdefault(identity, value)

    ordered = sorted(
        counts,
        key=lambda identity: (-counts[identity], str(labels[identity]).casefold()),
    )
    visible = ordered[:limit]
    result: dict[str, Any] = {
        "values": [
            {"value": labels[identity], "count": counts[identity]}
            for identity in visible
        ],
        "total_values": len(ordered),
        "truncated": len(visible) < len(ordered),
    }
    if missing_items:
        result["missing_items"] = missing_items
    return result


def _duration_summary(items: list[Any]) -> dict[str, Any]:
    """Return total duration while making missing-duration rows explicit."""
    total_ms = 0.0
    present = 0
    for item in items:
        duration = object.__getattribute__(item, "__dict__").get("duration")
        if duration is None:
            continue
        try:
            value = float(duration)
        except (TypeError, ValueError):
            continue
        if value < 0:
            continue
        total_ms += value
        present += 1

    return {
        "total_duration_minutes": round(total_ms / 60_000, 1),
        "duration_items": present,
        "duration_missing_items": len(items) - present,
    }


def _library_summary(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return exact count/facet aggregates for one typed Plex library query."""
    context: PlexUserContext = resolve_user_context(
        client,
        criteria.get("user"),
        criteria.get("user_id"),
    )
    media_type = str(criteria["media_type"])
    section = _resolve_query_section(
        client,
        context,
        media_type,
        criteria.get("library"),
        criteria.get("library_id"),
    )
    filters, post_filters = _build_filters(criteria)
    facets = _criterion_values(criteria.get("facets"))
    invalid_facets = [facet for facet in facets if facet not in LIBRARY_SUMMARY_FACETS]
    if invalid_facets:
        raise PlexExtendedError(
            "Unsupported library-summary facets: " + ", ".join(invalid_facets)
        )
    facet_limit = _normalized_facet_limit(criteria.get("facet_limit"))
    include_total_duration = bool(criteria.get("include_total_duration", False))

    needs_items = bool(facets or include_total_duration or post_filters)
    items: list[Any] | None = None
    if needs_items:
        items = _matching_items(
            section,
            media_type,
            criteria.get("title"),
            filters,
            post_filters,
        )
        count = len(items)
    else:
        count = _server_filtered_count(
            section,
            media_type,
            criteria.get("title"),
            filters,
        )
        if count is None:
            items = _matching_items(
                section,
                media_type,
                criteria.get("title"),
                filters,
                post_filters,
            )
            count = len(items)

    result: dict[str, Any] = {
        "success": True,
        "count": count,
        "library": str(section.title),
        "library_id": str(section.key),
        "media_type": media_type,
    }
    result.update(context.response_fields())

    if facets or include_total_duration:
        if items is None:
            items = _matching_items(
                section,
                media_type,
                criteria.get("title"),
                filters,
                post_filters,
            )

        if include_total_duration or any(
            facet in _HYDRATED_FACETS for facet in facets
        ):
            items = _hydrate_items(context.server, items)

        if include_total_duration:
            result.update(_duration_summary(items))
        if facets:
            result["facets"] = {
                facet: _facet_summary(items, facet, facet_limit) for facet in facets
            }

    return result


async def async_library_summary(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Run aggregate library analysis through the client's executor lock."""
    return await client._async_run(_library_summary, client, dict(criteria))
