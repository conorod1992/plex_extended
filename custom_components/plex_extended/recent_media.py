"""Recent-media queries for Plex Extended."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .client import PlexExtendedClient, PlexExtendedError
from .const import DEFAULT_LIMIT, HISTORY_PAGE_SIZE, MAX_LIMIT, RECENT_TV_GROUPINGS
from .user_context import _effective_selectors, resolve_user_context

_RECENT_GROUP_SCAN_MULTIPLIER = 20
_RECENT_GROUP_SCAN_MIN = 100
_RECENT_GROUP_SCAN_MAX = 1000

_SECTION_MEDIA_TYPES: dict[str, tuple[str, ...]] = {
    "movie": ("movie", "collection"),
    "show": ("show", "season", "episode", "collection"),
    "artist": ("artist", "album", "track", "collection"),
}


@dataclass(slots=True)
class RecentWindow:
    """Normalized absolute time window for a recent-media query."""

    since: datetime | None = None
    before: datetime | None = None
    within_days: int | None = None

    def response_fields(self) -> dict[str, Any]:
        """Return normalized window metadata for response data."""
        if self.since is None and self.before is None and self.within_days is None:
            return {}
        result: dict[str, Any] = {}
        if self.since is not None:
            result["since"] = self.since.isoformat()
        if self.before is not None:
            result["before"] = self.before.isoformat()
        if self.within_days is not None:
            result["within_days"] = self.within_days
        return {"window": result}


def _timezone(client: PlexExtendedClient) -> ZoneInfo:
    """Return the Home Assistant timezone, falling back safely if unavailable."""
    try:
        name = str(client.hass.config.time_zone)
        return ZoneInfo(name)
    except (AttributeError, ZoneInfoNotFoundError):
        local = datetime.now().astimezone().tzinfo
        if isinstance(local, ZoneInfo):
            return local
        return ZoneInfo("UTC")


def _parse_boundary(value: Any, timezone: ZoneInfo, label: str) -> datetime | None:
    """Parse an ISO date/datetime boundary in the Home Assistant timezone."""
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        if len(text) == 10:
            parsed_date = date.fromisoformat(text)
            return datetime.combine(parsed_date, time.min, tzinfo=timezone)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as err:
        raise PlexExtendedError(
            f"Invalid {label}: use an ISO date or datetime such as 2026-09-01 or "
            "2026-09-01T18:30:00+01:00"
        ) from err
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def _window(client: PlexExtendedClient, criteria: dict[str, Any]) -> RecentWindow:
    """Normalize since/before/within_days and reject contradictory windows."""
    timezone = _timezone(client)
    within_days = criteria.get("within_days")
    if within_days is not None:
        try:
            within_days = int(within_days)
        except (TypeError, ValueError) as err:
            raise PlexExtendedError("within_days must be a positive integer") from err
        if within_days < 1:
            raise PlexExtendedError("within_days must be at least 1")
        if criteria.get("since") or criteria.get("before"):
            raise PlexExtendedError(
                "within_days cannot be combined with since or before"
            )
        now = datetime.now(timezone)
        return RecentWindow(
            since=now - timedelta(days=within_days),
            within_days=within_days,
        )

    since = _parse_boundary(criteria.get("since"), timezone, "since")
    before = _parse_boundary(criteria.get("before"), timezone, "before")
    if since is not None and before is not None and since >= before:
        raise PlexExtendedError("since must be earlier than before")
    return RecentWindow(since=since, before=before)


def _epoch(value: datetime | None) -> int | None:
    """Return whole epoch seconds for an aware datetime."""
    return int(value.timestamp()) if value is not None else None


def _item_epoch(item: Any, attribute: str) -> int | None:
    """Return an item's Plex datetime attribute as epoch seconds."""
    value = getattr(item, attribute, None)
    if value is None:
        return None
    timestamp = getattr(value, "timestamp", None)
    if callable(timestamp):
        try:
            return int(timestamp())
        except (OSError, OverflowError, ValueError):
            return None
    return None


def _recent_fetch_limit(limit: int, grouping: str) -> int:
    """Fetch extra episodes when grouping may collapse many rows into one result."""
    if grouping == "none":
        return limit
    return min(
        _RECENT_GROUP_SCAN_MAX,
        max(_RECENT_GROUP_SCAN_MIN, limit * _RECENT_GROUP_SCAN_MULTIPLIER),
    )


def _section_types(section: Any, media_types: set[str], grouping: str) -> list[str]:
    """Return media types to query for one Plex section."""
    section_type = str(getattr(section, "type", ""))
    supported = _SECTION_MEDIA_TYPES.get(section_type, ())
    if media_types:
        return [media_type for media_type in supported if media_type in media_types]
    if grouping != "none" and section_type == "show":
        return ["episode"]
    return [section_type] if section_type else []


def _added_filters(window: RecentWindow) -> dict[str, Any]:
    """Build Plex-native Date Added filters."""
    filters: dict[str, Any] = {}
    if window.since is not None:
        # Plex's date "after" operator is strict, so subtract one second to make
        # the public since boundary inclusive at Plex's one-second precision.
        filters["addedAt>>"] = window.since - timedelta(seconds=1)
    if window.before is not None:
        filters["addedAt<<"] = window.before
    return filters


def _group_key(item: Any, grouping: str) -> tuple[Any, ...]:
    """Return a stable key for an episode grouping."""
    show_key = getattr(item, "grandparentRatingKey", None) or getattr(
        item, "grandparentKey", None
    )
    show_title = getattr(item, "grandparentTitle", None) or "Unknown show"
    library_id = getattr(item, "librarySectionID", None)
    if grouping == "season":
        return (library_id, show_key or show_title, getattr(item, "parentIndex", None))
    return (library_id, show_key or show_title)


def _group_episodes(
    client: PlexExtendedClient,
    items: list[Any],
    grouping: str,
) -> list[tuple[int, dict[str, Any]]]:
    """Group episode additions by show or season while retaining compact detail."""
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    passthrough: list[tuple[int, dict[str, Any]]] = []

    for item in items:
        added_epoch = _item_epoch(item, "addedAt") or 0
        if grouping == "none" or str(getattr(item, "type", "")) != "episode":
            passthrough.append(
                (
                    added_epoch,
                    client._serialize_item(item, include_summary=False),
                )
            )
            continue

        key = _group_key(item, grouping)
        show_title = getattr(item, "grandparentTitle", None) or "Unknown show"
        season = getattr(item, "parentIndex", None)
        serialized = client._serialize_item(item, include_summary=False)
        watched = bool(serialized.get("watched", False))
        current = groups.get(key)
        if current is None:
            current = {
                "type": (
                    "season_addition_group"
                    if grouping == "season"
                    else "show_addition_group"
                ),
                "group_by": grouping,
                "title": show_title,
                "show_title": show_title,
                "library": getattr(item, "librarySectionTitle", None),
                "library_id": getattr(item, "librarySectionID", None),
                "episodes_added": 0,
                "watched_episodes": 0,
                "remaining_episodes": 0,
                "seasons": set(),
                "newest_added_at": None,
                "oldest_added_at": None,
                "latest_episode": None,
                "_newest_epoch": -1,
                "_oldest_epoch": None,
            }
            show_rating_key = getattr(item, "grandparentRatingKey", None)
            if show_rating_key is not None:
                current["show_rating_key"] = str(show_rating_key)
            if grouping == "season":
                current["season"] = season
                season_rating_key = getattr(item, "parentRatingKey", None)
                if season_rating_key is not None:
                    current["season_rating_key"] = str(season_rating_key)
            groups[key] = current

        current["episodes_added"] += 1
        current["watched_episodes"] += int(watched)
        current["remaining_episodes"] += int(not watched)
        if season is not None:
            current["seasons"].add(int(season))

        added_at = serialized.get("added_at")
        if added_epoch > current["_newest_epoch"]:
            current["_newest_epoch"] = added_epoch
            current["newest_added_at"] = added_at
            current["latest_episode"] = serialized
        if current["_oldest_epoch"] is None or added_epoch < current["_oldest_epoch"]:
            current["_oldest_epoch"] = added_epoch
            current["oldest_added_at"] = added_at

    grouped: list[tuple[int, dict[str, Any]]] = []
    for current in groups.values():
        sort_epoch = int(current.pop("_newest_epoch"))
        current.pop("_oldest_epoch", None)
        seasons = sorted(current["seasons"])
        if grouping == "show":
            current["seasons"] = seasons
        else:
            current.pop("seasons", None)
        current = {
            key: value
            for key, value in current.items()
            if value not in (None, [], "")
        }
        grouped.append((sort_epoch, current))

    return passthrough + grouped


def _recently_added(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return recent additions with optional time windows and TV grouping."""
    context = resolve_user_context(
        client,
        criteria.get("user"),
        criteria.get("user_id"),
    )
    window = _window(client, criteria)
    grouping = str(criteria.get("group_tv_by", "none"))
    if grouping not in RECENT_TV_GROUPINGS:
        raise PlexExtendedError(f"Unsupported TV grouping: {grouping}")

    max_results = client._normalize_limit(criteria.get("limit", DEFAULT_LIMIT))
    include_summary = bool(criteria.get("include_summary", True))
    media_types = set(criteria.get("media_types") or [])

    # Preserve the exact existing Plex recently-added path when no new filtering
    # behavior is requested.
    if (
        window.since is None
        and window.before is None
        and grouping == "none"
    ):
        result = client._recently_added(
            max_results,
            criteria.get("library"),
            criteria.get("media_types"),
            include_summary,
            criteria.get("library_id"),
            context.server,
        )
        result.update(context.response_fields())
        return result

    selected_section = client._section(
        criteria.get("library"),
        criteria.get("library_id"),
        context.server,
    )
    sections = [selected_section] if selected_section else context.server.library.sections()
    fetch_limit = _recent_fetch_limit(max_results, grouping)
    filters = _added_filters(window)

    items: list[Any] = []
    seen: set[tuple[str, str]] = set()
    for section in sections:
        for media_type in _section_types(section, media_types, grouping):
            if filters:
                found = section.search(
                    sort="addedAt:desc",
                    maxresults=fetch_limit,
                    libtype=media_type,
                    filters=filters,
                )
            else:
                found = section.recentlyAdded(
                    maxresults=fetch_limit,
                    libtype=media_type,
                )
            for item in found:
                rating_key = getattr(item, "ratingKey", None)
                item_type = str(getattr(item, "type", ""))
                identity = (item_type, str(rating_key))
                if rating_key is not None and identity in seen:
                    continue
                if rating_key is not None:
                    seen.add(identity)
                items.append(item)

    items.sort(key=lambda item: _item_epoch(item, "addedAt") or 0, reverse=True)

    if grouping == "none":
        result_items = [
            client._serialize_item(item, include_summary=include_summary)
            for item in items[:max_results]
        ]
        underlying_count = len(result_items)
    else:
        grouped = _group_episodes(client, items, grouping)
        grouped.sort(key=lambda value: value[0], reverse=True)
        result_items = [value[1] for value in grouped[:max_results]]
        underlying_count = sum(
            int(item.get("episodes_added", 1)) for item in result_items
        )

    result: dict[str, Any] = {
        "success": True,
        "count": len(result_items),
        "media_item_count": underlying_count,
        "group_tv_by": grouping,
        "results": result_items,
    }
    result.update(window.response_fields())
    result.update(context.response_fields())
    return result


async def async_recently_added(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return recent additions through the client's executor lock."""
    return await client._async_run(_recently_added, client, dict(criteria))


def _history_key(
    account_id: int | None,
    section_id: Any | None,
    since_epoch: int | None,
) -> str:
    """Build Plex's history endpoint with the documented lower time bound."""
    args: list[tuple[str, str]] = [("sort", "viewedAt:desc")]
    if account_id is not None:
        args.append(("accountID", str(account_id)))
    if section_id is not None:
        args.append(("librarySectionID", str(section_id)))
    if since_epoch is not None:
        # PlexAPI itself uses the viewedAt> key, which serializes as viewedAt>=N.
        args.append(("viewedAt>", str(since_epoch - 1)))
    return f"/status/sessions/history/all?{urlencode(args)}"


def _recently_watched(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return watch history with an exact bounded time window."""
    window = _window(client, criteria)
    user, user_id = _effective_selectors(
        client,
        criteria.get("user"),
        criteria.get("user_id"),
    )

    # Preserve the existing paging implementation exactly when no window is used.
    if window.since is None and window.before is None:
        result = client._recently_watched(
            criteria.get("limit", DEFAULT_LIMIT),
            criteria.get("library"),
            user,
            criteria.get("media_types"),
            bool(criteria.get("include_summary", True)),
            criteria.get("library_id"),
            user_id,
        )
        if user is not None or user_id is not None:
            users = client._user_map()
            account_id = client._resolve_user_id(users, user, user_id)
            if account_id is not None:
                result.update({"user_id": account_id, "user": users[account_id]})
        return result

    server = client._require_server()
    max_results = client._normalize_limit(criteria.get("limit", DEFAULT_LIMIT))
    section = client._section(criteria.get("library"), criteria.get("library_id"))
    users = client._user_map()
    account_id = client._resolve_user_id(users, user, user_id)
    media_types = set(criteria.get("media_types") or [])
    include_summary = bool(criteria.get("include_summary", True))
    since_epoch = _epoch(window.since)
    before_epoch = _epoch(window.before)
    history_key = _history_key(
        account_id,
        section.key if section else None,
        since_epoch,
    )

    matched: list[Any] = []
    offset = 0
    lower_boundary_reached = False
    while len(matched) < max_results and not lower_boundary_reached:
        page = list(
            server.fetchItems(
                history_key,
                container_start=offset,
                container_size=HISTORY_PAGE_SIZE,
                maxresults=HISTORY_PAGE_SIZE,
            )
        )
        if not page:
            break

        for item in page:
            viewed_epoch = _item_epoch(item, "viewedAt")
            if viewed_epoch is None:
                continue
            if before_epoch is not None and viewed_epoch >= before_epoch:
                continue
            if since_epoch is not None and viewed_epoch < since_epoch:
                lower_boundary_reached = True
                break
            if media_types and getattr(item, "type", None) not in media_types:
                continue
            matched.append(item)
            if len(matched) >= max_results:
                break

        if len(page) < HISTORY_PAGE_SIZE:
            break
        offset += HISTORY_PAGE_SIZE

    result: dict[str, Any] = {
        "success": True,
        "count": len(matched),
        "results": [
            client._serialize_item(
                item,
                include_summary=include_summary,
                users=users,
            )
            for item in matched
        ],
    }
    result.update(window.response_fields())
    if account_id is not None:
        result.update({"user_id": account_id, "user": users[account_id]})
    return result


async def async_recently_watched(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return watch history through the client's executor lock."""
    return await client._async_run(_recently_watched, client, dict(criteria))
