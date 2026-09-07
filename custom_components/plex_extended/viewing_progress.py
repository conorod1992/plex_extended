"""TV viewing-progress queries for Plex Extended."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .client import PlexExtendedClient, PlexExtendedError


def _episode_sort_key(episode: Any) -> tuple[int, int, str]:
    """Return a stable canonical episode-order key."""
    season = getattr(episode, "parentIndex", None)
    number = getattr(episode, "index", None)
    return (
        int(season) if season is not None else 999_999,
        int(number) if number is not None else 999_999,
        str(getattr(episode, "title", "")),
    )


def _activity_key(episode: Any) -> str:
    """Return a sortable ISO-like last-viewed value."""
    value = getattr(episode, "lastViewedAt", None)
    if value is None:
        return ""
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)


def _is_played(episode: Any) -> bool:
    """Return whether Plex considers an episode fully played."""
    try:
        if hasattr(episode, "isPlayed"):
            return bool(episode.isPlayed)
    except Exception:
        pass
    return bool(getattr(episode, "viewCount", 0))


def _is_in_progress(episode: Any) -> bool:
    """Return whether an episode has progress but is not fully played."""
    return not _is_played(episode) and int(getattr(episode, "viewOffset", 0) or 0) > 0


def _episode_payload(
    client: PlexExtendedClient,
    episode: Any | None,
    *,
    include_summary: bool,
) -> dict[str, Any] | None:
    """Serialize an episode with a compact SxxExx label."""
    if episode is None:
        return None
    result = client._serialize_item(episode, include_summary=include_summary)
    season = getattr(episode, "parentIndex", None)
    number = getattr(episode, "index", None)
    if season is not None and number is not None:
        result["season_episode"] = f"S{int(season):02d}E{int(number):02d}"
    return result


def _resolve_tv_section(
    client: PlexExtendedClient,
    library: str | None,
    library_id: str | int | None,
) -> Any | None:
    """Resolve an optional TV library and reject non-TV sections."""
    if not library and library_id is None:
        return None
    section = client._section(library, library_id)
    assert section is not None
    if str(getattr(section, "type", "")) != "show":
        raise PlexExtendedError(
            f"Plex library '{section.title}' is not a TV-show library"
        )
    return section


def _candidate_label(show: Any) -> str:
    """Return a useful ambiguity label without exposing unrelated metadata."""
    title = str(getattr(show, "title", "Unknown"))
    year = getattr(show, "year", None)
    rating_key = getattr(show, "ratingKey", None)
    suffix: list[str] = []
    if year is not None:
        suffix.append(str(year))
    if rating_key is not None:
        suffix.append(f"rating_key {rating_key}")
    return f"{title} ({', '.join(suffix)})" if suffix else title


def _resolve_show(
    client: PlexExtendedClient,
    *,
    rating_key: str | None,
    title: str | None,
    year: int | None,
    library: str | None,
    library_id: str | int | None,
) -> Any:
    """Resolve one show by stable rating key or an unambiguous title search."""
    server = client._require_server()
    section = _resolve_tv_section(client, library, library_id)

    if rating_key:
        show = server.fetchItem(rating_key)
        if str(getattr(show, "type", "")) != "show":
            raise PlexExtendedError(
                f"Plex rating key {rating_key} is not a TV show"
            )
        if section is not None and str(getattr(show, "librarySectionID", "")) != str(
            section.key
        ):
            raise PlexExtendedError(
                f"Plex rating key {rating_key} is not in library '{section.title}'"
            )
        if title and str(getattr(show, "title", "")).casefold() != title.casefold():
            raise PlexExtendedError(
                f"Plex rating key {rating_key} is '{show.title}', not '{title}'"
            )
        if year is not None and int(getattr(show, "year", -1) or -1) != int(year):
            raise PlexExtendedError(
                f"Plex rating key {rating_key} does not match year {year}"
            )
        return show

    if not title:
        raise PlexExtendedError("Provide either rating_key or title")

    matches = server.search(
        title,
        mediatype="show",
        limit=25,
        sectionId=section.key if section is not None else None,
    )

    valid_section_ids: set[str] | None = None
    if section is None:
        valid_section_ids = {
            str(candidate.key)
            for candidate in server.library.sections()
            if str(getattr(candidate, "type", "")) == "show"
        }

    candidates = [
        item
        for item in matches
        if str(getattr(item, "type", "")) == "show"
        and getattr(item, "ratingKey", None) is not None
        and getattr(item, "librarySectionID", None) is not None
        and (
            section is not None
            or str(getattr(item, "librarySectionID", "")) in (valid_section_ids or set())
        )
    ]

    if year is not None:
        candidates = [
            item for item in candidates if int(getattr(item, "year", -1) or -1) == int(year)
        ]

    exact = [
        item
        for item in candidates
        if str(getattr(item, "title", "")).casefold() == title.casefold()
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        choices = "; ".join(_candidate_label(item) for item in exact[:5])
        raise PlexExtendedError(
            f"Multiple Plex shows exactly match '{title}'. Use rating_key to select one: "
            f"{choices}"
        )

    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        year_text = f" from {year}" if year is not None else ""
        raise PlexExtendedError(f"Plex show not found: {title}{year_text}")

    choices = "; ".join(_candidate_label(item) for item in candidates[:5])
    raise PlexExtendedError(
        f"Plex show title '{title}' is ambiguous. Use rating_key or a year: {choices}"
    )


def _season_summaries(episodes: list[Any]) -> list[dict[str, Any]]:
    """Summarize progress by season."""
    grouped: dict[int, list[Any]] = defaultdict(list)
    for episode in episodes:
        season = getattr(episode, "parentIndex", None)
        if season is None:
            continue
        grouped[int(season)].append(episode)

    result: list[dict[str, Any]] = []
    for season in sorted(grouped):
        season_episodes = grouped[season]
        total = len(season_episodes)
        watched = sum(1 for episode in season_episodes if _is_played(episode))
        in_progress = sum(
            1 for episode in season_episodes if _is_in_progress(episode)
        )
        result.append(
            {
                "season": season,
                "total_episodes": total,
                "watched_episodes": watched,
                "unwatched_episodes": total - watched,
                "in_progress_episodes": in_progress,
                "completion_percent": round((watched / total) * 100, 1)
                if total
                else 0.0,
                "complete": bool(total and watched == total),
            }
        )
    return result


def _watch_status(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return viewing progress for one TV show."""
    include_summary = bool(criteria.get("include_summary", True))
    include_seasons = bool(criteria.get("include_seasons", True))
    include_specials = bool(criteria.get("include_specials", False))

    show = _resolve_show(
        client,
        rating_key=criteria.get("rating_key"),
        title=criteria.get("title"),
        year=criteria.get("year"),
        library=criteria.get("library"),
        library_id=criteria.get("library_id"),
    )

    episodes = list(show.episodes())
    if not include_specials:
        episodes = [
            episode for episode in episodes if int(getattr(episode, "parentIndex", 0) or 0) != 0
        ]
    episodes.sort(key=_episode_sort_key)

    total = len(episodes)
    watched_items = [episode for episode in episodes if _is_played(episode)]
    in_progress_items = [episode for episode in episodes if _is_in_progress(episode)]
    unwatched = total - len(watched_items)
    complete = bool(total and len(watched_items) == total)

    if total == 0:
        status = "empty"
    elif complete:
        status = "complete"
    elif not watched_items and not in_progress_items:
        status = "unwatched"
    else:
        status = "in_progress"

    last_watched = None
    if watched_items:
        with_activity = [item for item in watched_items if _activity_key(item)]
        last_watched = (
            max(with_activity, key=_activity_key)
            if with_activity
            else max(watched_items, key=_episode_sort_key)
        )

    last_activity = None
    activity_items = [item for item in episodes if _activity_key(item)]
    if activity_items:
        last_activity = max(activity_items, key=_activity_key)

    in_progress_episode = None
    if in_progress_items:
        with_activity = [item for item in in_progress_items if _activity_key(item)]
        in_progress_episode = (
            max(with_activity, key=_activity_key)
            if with_activity
            else min(in_progress_items, key=_episode_sort_key)
        )

    next_episode = None
    if not complete and episodes:
        try:
            candidate = show.onDeck()
        except Exception:
            candidate = None
        if candidate is not None:
            candidate_season = int(getattr(candidate, "parentIndex", 0) or 0)
            if include_specials or candidate_season != 0:
                next_episode = candidate
        if next_episode is None:
            next_episode = next(
                (episode for episode in episodes if not _is_played(episode)),
                None,
            )

    show_data = client._serialize_item(show, include_summary=include_summary)
    result: dict[str, Any] = {
        "success": True,
        "status": status,
        "complete": complete,
        "total_episodes": total,
        "watched_episodes": len(watched_items),
        "unwatched_episodes": unwatched,
        "in_progress_episodes": len(in_progress_items),
        "completion_percent": round((len(watched_items) / total) * 100, 1)
        if total
        else 0.0,
        "include_specials": include_specials,
        "show": show_data,
        "last_watched_episode": _episode_payload(
            client, last_watched, include_summary=include_summary
        ),
        "last_activity_episode": _episode_payload(
            client, last_activity, include_summary=include_summary
        ),
        "in_progress_episode": _episode_payload(
            client, in_progress_episode, include_summary=include_summary
        ),
        "next_episode": _episode_payload(
            client, next_episode, include_summary=include_summary
        ),
    }
    if include_seasons:
        result["seasons"] = _season_summaries(episodes)
    return result


async def async_watch_status(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return TV viewing progress through the client's executor lock."""
    return await client._async_run(_watch_status, client, dict(criteria))
