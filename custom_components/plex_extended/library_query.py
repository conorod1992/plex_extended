"""Typed advanced Plex library queries for Plex Extended."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .client import PlexExtendedClient, PlexExtendedError
from .const import DEFAULT_LIMIT

_SECTION_TYPE_BY_MEDIA_TYPE = {
    "movie": "movie",
    "show": "show",
    "season": "show",
    "episode": "show",
    "artist": "artist",
    "album": "artist",
    "track": "artist",
}

_SORT_FIELDS = {
    "title": "titleSort",
    "year": "year",
    "added_at": "addedAt",
    "last_viewed_at": "lastViewedAt",
    "critic_rating": "rating",
    "audience_rating": "audienceRating",
    "user_rating": "userRating",
    "duration": "duration",
    "resolution": "mediaHeight",
}


def _values(value: Any) -> list[str]:
    """Return non-empty string values from a scalar or iterable."""
    if value is None:
        return []
    if isinstance(value, str):
        values: Iterable[Any] = [value]
    else:
        values = value
    return [str(item).strip() for item in values if str(item).strip()]


def _tag_names(values: Iterable[Any] | None) -> list[str]:
    """Return names from Plex tag-like objects."""
    if not values:
        return []
    result: list[str] = []
    for value in values:
        name = getattr(value, "tag", None) or getattr(value, "title", None)
        if name:
            result.append(str(name))
    return result


def _validate_range(
    minimum: int | float | None,
    maximum: int | float | None,
    label: str,
) -> None:
    """Reject inverted numeric ranges."""
    if minimum is not None and maximum is not None and minimum > maximum:
        raise PlexExtendedError(f"{label} minimum cannot be greater than maximum")


def _resolve_query_section(
    client: PlexExtendedClient,
    media_type: str,
    library: str | None,
    library_id: str | int | None,
) -> Any:
    """Resolve or safely infer the library section for an advanced query."""
    expected_type = _SECTION_TYPE_BY_MEDIA_TYPE.get(media_type)
    if expected_type is None:
        raise PlexExtendedError(f"Unsupported query media type: {media_type}")

    if library or library_id is not None:
        section = client._section(library, library_id)
        assert section is not None
        section_type = str(getattr(section, "type", ""))
        if section_type != expected_type:
            raise PlexExtendedError(
                f"Plex library '{section.title}' has type '{section_type}' and cannot "
                f"be queried for '{media_type}' items"
            )
        return section

    sections = [
        section
        for section in client._require_server().library.sections()
        if str(getattr(section, "type", "")) == expected_type
    ]
    if not sections:
        raise PlexExtendedError(
            f"No Plex library supports '{media_type}' queries. Select a library explicitly."
        )
    if len(sections) > 1:
        choices = ", ".join(
            f"{section.title} (ID {section.key})" for section in sections
        )
        raise PlexExtendedError(
            f"Multiple Plex libraries support '{media_type}' queries. Use library or "
            f"library_id to select one: {choices}"
        )
    return sections[0]


def _build_filters(criteria: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build Plex server filters and PlexAPI post-filters from typed criteria."""
    filters: dict[str, Any] = {}
    post_filters: dict[str, Any] = {}

    genres = _values(criteria.get("genres"))
    if genres:
        filters["genre"] = genres
    genres_all = _values(criteria.get("genres_all"))
    if genres_all:
        filters["genre&"] = genres_all

    for input_key, plex_key in (
        ("actors", "actor"),
        ("directors", "director"),
        ("collections", "collection"),
        ("content_ratings", "contentRating"),
        ("studios", "studio"),
        ("resolutions", "resolution"),
    ):
        values = _values(criteria.get(input_key))
        if values:
            filters[plex_key] = values

    year = criteria.get("year")
    year_min = criteria.get("year_min")
    year_max = criteria.get("year_max")
    _validate_range(year_min, year_max, "Year")
    if year is not None:
        filters["year"] = int(year)
    if year_min is not None:
        # Plex's integer operators are strict (> / <). Offset by one to expose
        # intuitive inclusive min/max fields to Home Assistant callers.
        filters["year>>"] = int(year_min) - 1
    if year_max is not None:
        filters["year<<"] = int(year_max) + 1

    decade = criteria.get("decade")
    if decade is not None:
        filters["decade"] = int(decade)

    watched_state = criteria.get("watched_state", "any")
    if watched_state == "watched":
        filters["unwatched!"] = True
    elif watched_state == "unwatched":
        filters["unwatched"] = True
    elif watched_state == "in_progress":
        filters["inProgress"] = True
    elif watched_state != "any":
        raise PlexExtendedError(f"Unsupported watched state: {watched_state}")

    hdr_state = criteria.get("hdr", "any")
    if hdr_state == "hdr":
        filters["hdr"] = True
    elif hdr_state == "sdr":
        filters["hdr!"] = True
    elif hdr_state != "any":
        raise PlexExtendedError(f"Unsupported HDR state: {hdr_state}")

    for input_key, plex_key in (
        ("added_after", "addedAt>>"),
        ("added_before", "addedAt<<"),
        ("last_viewed_after", "lastViewedAt>>"),
        ("last_viewed_before", "lastViewedAt<<"),
    ):
        value = criteria.get(input_key)
        if value:
            filters[plex_key] = str(value)

    for prefix, plex_attribute in (
        ("critic_rating", "rating"),
        ("audience_rating", "audienceRating"),
        ("user_rating", "userRating"),
    ):
        minimum = criteria.get(f"{prefix}_min")
        maximum = criteria.get(f"{prefix}_max")
        _validate_range(minimum, maximum, prefix.replace("_", " ").title())
        if minimum is not None:
            post_filters[f"{plex_attribute}__gte"] = float(minimum)
        if maximum is not None:
            post_filters[f"{plex_attribute}__lte"] = float(maximum)

    duration_min = criteria.get("duration_min_minutes")
    duration_max = criteria.get("duration_max_minutes")
    _validate_range(duration_min, duration_max, "Duration")
    if duration_min is not None:
        post_filters["duration__gte"] = int(float(duration_min) * 60_000)
    if duration_max is not None:
        post_filters["duration__lte"] = int(float(duration_max) * 60_000)

    return filters, post_filters


def _build_sort(criteria: dict[str, Any]) -> str | None:
    """Build a safe Plex sort string from a friendly field name."""
    sort_by = criteria.get("sort_by")
    if not sort_by:
        return None
    plex_field = _SORT_FIELDS.get(str(sort_by))
    if plex_field is None:
        raise PlexExtendedError(f"Unsupported sort field: {sort_by}")

    sort_order = criteria.get("sort_order")
    if sort_order is None:
        sort_order = "asc" if sort_by == "title" else "desc"
    if sort_order not in ("asc", "desc"):
        raise PlexExtendedError(f"Unsupported sort order: {sort_order}")
    return f"{plex_field}:{sort_order}"


def _serialize_query_item(
    client: PlexExtendedClient,
    item: Any,
    *,
    include_summary: bool,
    include_technical: bool,
) -> dict[str, Any]:
    """Serialize an advanced-query result with useful relationship metadata."""
    if include_technical:
        rating_key = getattr(item, "ratingKey", None)
        if rating_key is not None:
            item = client._require_server().fetchItem(rating_key)

    result = client._serialize_item(
        item,
        include_summary=include_summary,
        include_technical=include_technical,
    )
    actors = _tag_names(getattr(item, "roles", None))
    collections = _tag_names(getattr(item, "collections", None))
    if actors:
        result["actors"] = actors
    if collections:
        result["collections"] = collections
    return result


def _query_library(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Run a typed advanced query against one Plex library section."""
    media_type = str(criteria["media_type"])
    section = _resolve_query_section(
        client,
        media_type,
        criteria.get("library"),
        criteria.get("library_id"),
    )
    max_results = client._normalize_limit(criteria.get("limit", DEFAULT_LIMIT))
    filters, post_filters = _build_filters(criteria)
    sort = _build_sort(criteria)

    items = section.search(
        title=criteria.get("title") or None,
        sort=sort,
        maxresults=max_results,
        libtype=media_type,
        filters=filters or None,
        **post_filters,
    )

    include_summary = bool(criteria.get("include_summary", True))
    include_technical = bool(criteria.get("include_technical", False))
    results = [
        _serialize_query_item(
            client,
            item,
            include_summary=include_summary,
            include_technical=include_technical,
        )
        for item in list(items)[:max_results]
    ]

    return {
        "success": True,
        "count": len(results),
        "library": str(section.title),
        "library_id": str(section.key),
        "media_type": media_type,
        "results": results,
    }


async def async_query_library(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Run an advanced Plex library query through the client's executor lock."""
    return await client._async_run(_query_library, client, dict(criteria))
