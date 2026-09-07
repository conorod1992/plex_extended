"""Per-user Plex server context for Plex Extended."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from plexapi.exceptions import Unauthorized
from plexapi.server import PlexServer

from .client import PlexExtendedClient, PlexExtendedError
from .const import CONF_DEFAULT_USER_ID, DEFAULT_LIMIT


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
    users = client._user_map()
    user, user_id = _effective_selectors(client, user, user_id)
    account_id = client._resolve_user_id(users, user, user_id)

    if account_id is None:
        return PlexUserContext(base_server, None, None, users)

    name = users[account_id]

    # Plex Media Server reserves local system account ID 1 for the server
    # owner/admin. switchUser() intentionally resolves only other Plex users,
    # so the configured owner uses the already-authenticated base server.
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
