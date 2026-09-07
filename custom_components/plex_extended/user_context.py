"""Per-user Plex server context for Plex Extended."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from plexapi.exceptions import Unauthorized
from plexapi.server import PlexServer

from .client import PlexExtendedClient, PlexExtendedError
from .const import (
    CONF_DEFAULT_USER_ID,
    DEFAULT_LIMIT,
    DEFAULT_SEARCH_TYPES,
    MAX_LIMIT,
)


@dataclass(slots=True)
class PlexUserContext:
    """Resolved Plex user context for one query."""

    server: PlexServer
    user_id: int | None
    user: str | None
    users: dict[int, str]

    def response_fields(self) -> dict[str, Any]:
        """Return user identity fields suitable for top-level response data."""
        if self.user_id is None:
            return {}
        return {"user_id": self.user_id, "user": self.user}


def _configured_default_user_id(client: PlexExtendedClient) -> str | int | None:
    """Return the config-entry default Plex user ID, if configured."""
    entry = getattr(client, "entry", None)
    options = getattr(entry, "options", None)
    if not options:
        return None
    return options.get(CONF_DEFAULT_USER_ID)


def _effective_selectors(
    client: PlexExtendedClient,
    user: str | None,
    user_id: str | int | None,
) -> tuple[str | None, str | int | None]:
    """Apply the configured default only when the caller supplied no user."""
    if user is None and user_id is None:
        user_id = _configured_default_user_id(client)
    return user, user_id


def resolve_user_context(
    client: PlexExtendedClient,
    user: str | None = None,
    user_id: str | int | None = None,
) -> PlexUserContext:
    """Resolve a Plex server operating as the requested/default user."""
    base_server = client._require_server()
    user, user_id = _effective_selectors(client, user, user_id)
    if user is None and user_id is None:
        return PlexUserContext(base_server, None, None, {})

    users = client._user_map()
    account_id = client._resolve_user_id(users, user, user_id)
    if account_id is None:
        return PlexUserContext(base_server, None, None, users)

    name = users[account_id]

    # Local PMS account ID 1 represents the server owner. switchUser() resolves
    # only the owner's other linked/home users, so owner state is the base server
    # context. Household-user switching itself is only supported from owner auth.
    if account_id == 1:
        return PlexUserContext(base_server, account_id, name, users)

    cache = getattr(client, "_plex_extended_user_servers", None)
    if cache is None:
        cache = {}
        setattr(client, "_plex_extended_user_servers", cache)

    server = cache.get(account_id)
    if server is None:
        try:
            server = base_server.switchUser(name)
        except Unauthorized as err:
            raise PlexExtendedError(
                f"Plex rejected access for user '{name}'. The configured server account "
                "must be the server owner to query another user's viewing state."
            ) from err
        except Exception as err:
            raise PlexExtendedError(
                f"Unable to switch Plex context to user '{name}': {err}"
            ) from err
        cache[account_id] = server

    return PlexUserContext(server, account_id, name, users)


def resolve_section(
    client: PlexExtendedClient,
    server: PlexServer,
    library: str | None = None,
    library_id: str | int | None = None,
) -> Any | None:
    """Resolve a library against a specific user's Plex server view."""
    if not library and library_id is None:
        return None

    sections = server.library.sections()

    if library_id is not None:
        wanted_id = str(library_id)
        matches = [section for section in sections if str(section.key) == wanted_id]
        if not matches:
            raise PlexExtendedError(f"Plex library ID not found: {library_id}")
        section = matches[0]
        if library and section.title.casefold() != library.casefold():
            raise PlexExtendedError(
                f"Plex library ID {library_id} is '{section.title}', not '{library}'"
            )
        return section

    assert library is not None
    wanted = library.casefold()
    matches = [section for section in sections if section.title.casefold() == wanted]
    if not matches:
        raise PlexExtendedError(f"Plex library not found: {library}")
    if len(matches) > 1:
        ids = ", ".join(str(section.key) for section in matches)
        raise PlexExtendedError(
            f"Multiple Plex libraries are named '{library}'. Use library_id instead "
            f"(matching IDs: {ids})"
        )
    return matches[0]


def _search_for_context(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Search Plex through the selected user's server context."""
    context = resolve_user_context(
        client,
        criteria.get("user"),
        criteria.get("user_id"),
    )
    section = resolve_section(
        client,
        context.server,
        criteria.get("library"),
        criteria.get("library_id"),
    )
    section_id = section.key if section else None
    media_types = client._normalize_types(
        criteria.get("search_types") or DEFAULT_SEARCH_TYPES
    )
    requested_types = set(media_types)
    max_results = client._normalize_limit(criteria.get("limit", DEFAULT_LIMIT))
    mediatype = media_types[0] if len(media_types) == 1 else None

    matches = context.server.search(
        criteria["query"],
        mediatype=mediatype,
        limit=max_results,
        sectionId=section_id,
    )

    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    include_summary = bool(criteria.get("include_summary", True))
    include_technical = bool(criteria.get("include_technical", False))
    for match in matches:
        match_type = str(getattr(match, "type", ""))
        if match_type not in requested_types:
            continue
        match_library_id = getattr(match, "librarySectionID", None)
        rating_key = getattr(match, "ratingKey", None)
        if match_library_id is None or rating_key is None:
            continue
        if section_id is not None and str(match_library_id) != str(section_id):
            continue

        identity = (match_type, str(rating_key))
        if identity in seen:
            continue
        seen.add(identity)

        if include_technical:
            try:
                match = context.server.fetchItem(rating_key)
            except Exception:
                pass
        results.append(
            client._serialize_item(
                match,
                include_summary=include_summary,
                include_technical=include_technical,
            )
        )
        if len(results) >= max_results:
            break

    result: dict[str, Any] = {
        "success": True,
        "query": criteria["query"],
        "count": len(results),
        "results": results,
    }
    result.update(context.response_fields())
    return result


async def async_search_for_context(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Search Plex using explicit/default user viewing state."""
    return await client._async_run(_search_for_context, client, dict(criteria))


def _recently_added_for_context(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return recent additions with selected-user watch/progress metadata."""
    context = resolve_user_context(
        client,
        criteria.get("user"),
        criteria.get("user_id"),
    )
    max_results = client._normalize_limit(criteria.get("limit", DEFAULT_LIMIT))
    types = set(criteria.get("media_types") or [])
    section = resolve_section(
        client,
        context.server,
        criteria.get("library"),
        criteria.get("library_id"),
    )
    if section:
        items = section.recentlyAdded(maxresults=MAX_LIMIT)
    else:
        items = context.server.library.recentlyAdded()
    if types:
        items = [item for item in items if getattr(item, "type", None) in types]
    items = list(items)[:max_results]

    result: dict[str, Any] = {
        "success": True,
        "count": len(items),
        "results": [
            client._serialize_item(
                item,
                include_summary=bool(criteria.get("include_summary", True)),
            )
            for item in items
        ],
    }
    result.update(context.response_fields())
    return result


async def async_recently_added_for_context(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return recent additions using selected/default Plex user metadata."""
    return await client._async_run(
        _recently_added_for_context,
        client,
        dict(criteria),
    )


def _media_details_for_context(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return one Plex item's metadata in the selected user's context."""
    context = resolve_user_context(
        client,
        criteria.get("user"),
        criteria.get("user_id"),
    )
    item = context.server.fetchItem(criteria["rating_key"])
    result: dict[str, Any] = {
        "success": True,
        "result": client._serialize_item(
            item,
            include_summary=True,
            include_technical=bool(criteria.get("include_technical", True)),
        ),
    }
    result.update(context.response_fields())
    return result


async def async_media_details_for_context(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return item details using selected/default Plex user state."""
    return await client._async_run(
        _media_details_for_context,
        client,
        dict(criteria),
    )


def _recently_watched_for_context(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Apply default-user selection to the existing history backend."""
    user, user_id = _effective_selectors(
        client,
        criteria.get("user"),
        criteria.get("user_id"),
    )
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


async def async_recently_watched_for_context(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return history using explicit or configured-default user selection."""
    return await client._async_run(
        _recently_watched_for_context,
        client,
        dict(criteria),
    )


def _browse_for_context(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
    *,
    on_deck: bool,
) -> dict[str, Any]:
    """Return Continue Watching or On Deck for a selected Plex user."""
    context = resolve_user_context(
        client,
        criteria.get("user"),
        criteria.get("user_id"),
    )
    max_results = client._normalize_limit(criteria.get("limit", DEFAULT_LIMIT))
    section = resolve_section(
        client,
        context.server,
        criteria.get("library"),
        criteria.get("library_id"),
    )

    if on_deck:
        items = section.onDeck() if section else context.server.library.onDeck()
    else:
        items = (
            section.continueWatching()
            if section
            else context.server.continueWatching()
        )

    items = list(items)[:max_results]
    result: dict[str, Any] = {
        "success": True,
        "count": len(items),
        "results": [
            client._serialize_item(
                item,
                include_summary=bool(criteria.get("include_summary", True)),
            )
            for item in items
        ],
    }
    result.update(context.response_fields())
    return result


async def async_continue_watching_for_context(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return Continue Watching for an explicit/default Plex user."""
    return await client._async_run(
        _browse_for_context,
        client,
        dict(criteria),
        on_deck=False,
    )


async def async_on_deck_for_context(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return On Deck for an explicit/default Plex user."""
    return await client._async_run(
        _browse_for_context,
        client,
        dict(criteria),
        on_deck=True,
    )


def _validate_user_context(
    client: PlexExtendedClient,
    user_id: str | int,
) -> dict[str, Any]:
    """Validate that Plex can operate as a selected user."""
    context = resolve_user_context(client, user_id=user_id)
    # Force one lightweight user-scoped library read so a bad switched token or
    # unavailable user fails while saving options rather than during a later query.
    context.server.library.sections()
    return {"user_id": context.user_id, "user": context.user}


async def async_validate_user_context(
    client: PlexExtendedClient,
    user_id: str | int,
) -> dict[str, Any]:
    """Validate a default-user selection through the client's executor lock."""
    return await client._async_run(_validate_user_context, client, user_id)
