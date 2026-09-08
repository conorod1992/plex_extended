"""TV catch-up queries for Plex Extended."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .client import PlexExtendedClient, PlexExtendedError
from .const import DEFAULT_LIMIT
from .recent_media import RecentWindow, _added_filters, _item_epoch, _window
from .user_context import PlexUserContext, resolve_user_context
from .viewing_progress import _episode_sort_key, _is_in_progress, _is_played

_CANDIDATE_SCAN_LIMIT = 1000


@dataclass(slots=True)
class _CatchUpGroup:
    """Aggregate remaining episodes for one show."""

    title: str
    library: str | None
    library_id: Any | None
    show_rating_key: str | None
    episodes: list[Any] = field(default_factory=list)
    newest_epoch: int = 0
    oldest_epoch: int | None = None


def _tv_sections(
    client: PlexExtendedClient,
    server: Any,
    library: str | None,
    library_id: str | int | None,
) -> list[Any]:
    """Return one selected TV section or all TV sections visible to this user."""
    selected = client._section(library, library_id, server)
    if selected is not None:
        if str(getattr(selected, "type", "")) != "show":
            raise PlexExtendedError(
                f"Plex library '{selected.title}' is not a TV-show library"
            )
        return [selected]
    return [
        section
        for section in server.library.sections()
        if str(getattr(section, "type", "")) == "show"
    ]


def _in_window(item: Any, window: RecentWindow) -> bool:
    """Enforce the public inclusive-since/exclusive-before window client-side too."""
    if window.since is None and window.before is None:
        return True
    epoch = _item_epoch(item, "addedAt")
    if epoch is None:
        return False
    if window.since is not None and epoch < int(window.since.timestamp()):
        return False
    if window.before is not None and epoch >= int(window.before.timestamp()):
        return False
    return True


def _show_identity(item: Any) -> tuple[str, str]:
    """Return a stable grouping identity for an episode's parent show."""
    library_id = str(getattr(item, "librarySectionID", "") or "")
    show_key = getattr(item, "grandparentRatingKey", None) or getattr(
        item, "grandparentKey", None
    )
    if show_key is not None:
        return library_id, f"key:{show_key}"
    return library_id, f"title:{str(getattr(item, 'grandparentTitle', '')).casefold()}"


def _episode_payload(
    client: PlexExtendedClient,
    episode: Any,
    *,
    include_summary: bool,
) -> dict[str, Any]:
    """Serialize one remaining episode with catch-up-specific state."""
    result = client._serialize_item(episode, include_summary=include_summary)
    season = getattr(episode, "parentIndex", None)
    number = getattr(episode, "index", None)
    if season is not None and number is not None:
        result["season_episode"] = f"S{int(season):02d}E{int(number):02d}"
    result["in_progress"] = _is_in_progress(episode)
    return result


def _serialize_group(
    client: PlexExtendedClient,
    group: _CatchUpGroup,
    *,
    episode_limit: int,
    include_summary: bool,
) -> dict[str, Any]:
    """Serialize one show group without overstating omitted episode detail."""
    episodes = sorted(group.episodes, key=_episode_sort_key)
    in_progress_count = sum(1 for episode in episodes if _is_in_progress(episode))
    never_started_count = len(episodes) - in_progress_count
    seasons = sorted(
        {
            int(season)
            for episode in episodes
            if (season := getattr(episode, "parentIndex", None)) is not None
        }
    )
    returned = episodes[:episode_limit]
    result: dict[str, Any] = {
        "type": "tv_catch_up_group",
        "title": group.title,
        "show_title": group.title,
        "library": group.library,
        "library_id": group.library_id,
        "show_rating_key": group.show_rating_key,
        "remaining_episode_count": len(episodes),
        "unwatched_episode_count": never_started_count,
        "in_progress_episode_count": in_progress_count,
        "seasons": seasons,
        "newest_added_at": client._serialize_item(
            max(episodes, key=lambda item: _item_epoch(item, "addedAt") or 0),
            include_summary=False,
        ).get("added_at"),
        "oldest_added_at": client._serialize_item(
            min(episodes, key=lambda item: _item_epoch(item, "addedAt") or 0),
            include_summary=False,
        ).get("added_at"),
        "episodes_returned": len(returned),
        "episodes_truncated": len(episodes) > len(returned),
        "next_episode": _episode_payload(
            client,
            episodes[0],
            include_summary=include_summary,
        ),
        "episodes": [
            _episode_payload(client, episode, include_summary=include_summary)
            for episode in returned
        ],
    }
    return {
        key: value
        for key, value in result.items()
        if value not in (None, [], "") or key in {"episodes_truncated"}
    }


def _scan_section(
    section: Any,
    window: RecentWindow,
) -> tuple[list[Any], bool]:
    """Fetch a bounded, newest-first candidate set and report scan truncation."""
    filters = _added_filters(window)
    filters["unwatched"] = True
    found = list(
        section.search(
            sort="addedAt:desc",
            maxresults=_CANDIDATE_SCAN_LIMIT + 1,
            libtype="episode",
            filters=filters,
        )
    )
    truncated = len(found) > _CANDIDATE_SCAN_LIMIT
    return found[:_CANDIDATE_SCAN_LIMIT], truncated


def _tv_catch_up(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return remaining TV episodes grouped by show for one Plex user context."""
    context: PlexUserContext = resolve_user_context(
        client,
        criteria.get("user"),
        criteria.get("user_id"),
    )
    window = _window(client, criteria)
    include_specials = bool(criteria.get("include_specials", False))
    include_in_progress = bool(criteria.get("include_in_progress", True))
    include_summary = bool(criteria.get("include_summary", True))
    max_groups = client._normalize_limit(criteria.get("limit", DEFAULT_LIMIT))
    episode_limit = client._normalize_limit(criteria.get("episode_limit", DEFAULT_LIMIT))

    groups: dict[tuple[str, str], _CatchUpGroup] = {}
    seen: set[tuple[str, str]] = set()
    candidate_scan_truncated = False

    for section in _tv_sections(
        client,
        context.server,
        criteria.get("library"),
        criteria.get("library_id"),
    ):
        candidates, truncated = _scan_section(section, window)
        candidate_scan_truncated = candidate_scan_truncated or truncated
        for episode in candidates:
            if str(getattr(episode, "type", "")) != "episode":
                continue
            rating_key = getattr(episode, "ratingKey", None)
            identity = (str(getattr(episode, "librarySectionID", "")), str(rating_key))
            if rating_key is not None and identity in seen:
                continue
            if rating_key is not None:
                seen.add(identity)
            if not _in_window(episode, window):
                continue
            if not include_specials and int(getattr(episode, "parentIndex", 0) or 0) == 0:
                continue
            if _is_played(episode):
                continue
            in_progress = _is_in_progress(episode)
            if in_progress and not include_in_progress:
                continue

            group_key = _show_identity(episode)
            group = groups.get(group_key)
            if group is None:
                show_rating_key = getattr(episode, "grandparentRatingKey", None)
                group = _CatchUpGroup(
                    title=str(getattr(episode, "grandparentTitle", None) or "Unknown show"),
                    library=getattr(episode, "librarySectionTitle", None),
                    library_id=getattr(episode, "librarySectionID", None),
                    show_rating_key=(
                        str(show_rating_key) if show_rating_key is not None else None
                    ),
                )
                groups[group_key] = group
            group.episodes.append(episode)
            epoch = _item_epoch(episode, "addedAt") or 0
            group.newest_epoch = max(group.newest_epoch, epoch)
            group.oldest_epoch = (
                epoch
                if group.oldest_epoch is None
                else min(group.oldest_epoch, epoch)
            )

    ordered = sorted(
        groups.values(),
        key=lambda group: (-group.newest_epoch, group.title.casefold()),
    )
    returned_groups = ordered[:max_groups]

    remaining_episode_count = sum(len(group.episodes) for group in ordered)
    in_progress_episode_count = sum(
        1
        for group in ordered
        for episode in group.episodes
        if _is_in_progress(episode)
    )
    result: dict[str, Any] = {
        "success": True,
        "count": len(returned_groups),
        "matched_show_count": len(ordered),
        "remaining_episode_count": remaining_episode_count,
        "unwatched_episode_count": remaining_episode_count - in_progress_episode_count,
        "in_progress_episode_count": in_progress_episode_count,
        "results_truncated": len(ordered) > len(returned_groups),
        "candidate_scan_truncated": candidate_scan_truncated,
        "candidate_scan_limit_per_library": _CANDIDATE_SCAN_LIMIT,
        "include_specials": include_specials,
        "include_in_progress": include_in_progress,
        "results": [
            _serialize_group(
                client,
                group,
                episode_limit=episode_limit,
                include_summary=include_summary,
            )
            for group in returned_groups
        ],
    }
    result.update(window.response_fields())
    result.update(context.response_fields())
    return result


async def async_tv_catch_up(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return TV catch-up data through the client's executor lock."""
    return await client._async_run(_tv_catch_up, client, dict(criteria))
