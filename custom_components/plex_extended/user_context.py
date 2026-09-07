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
    result = client._search(
        criteria["query"],
        criteria.get("search_types"),
        criteria.get("limit", DEFAULT_LIMIT),
        criteria.get("library"),
        bool(criteria.get("include_summary", True)),
        bool(criteria.get("include_technical", False)),
        criteria.get("library_id"),
        context.server,
    )
    result.update(context.response_fields())
    return result


async def async_search_for_context(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Search Plex using explicit/default user viewing state."""
    return await client._async_run(_search_for_context, client, dict(criteria))


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
    result = client._media_details(
        criteria["rating_key"],
        bool(criteria.get("include_technical", True)),
        context.server,
    )
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
    if on_deck:
        result = client._on_deck(
            criteria.get("limit", DEFAULT_LIMIT),
            criteria.get("library"),
            bool(criteria.get("include_summary", True)),
            criteria.get("library_id"),
            context.server,
        )
    else:
        result = client._continue_watching(
            criteria.get("limit", DEFAULT_LIMIT),
            criteria.get("library"),
            bool(criteria.get("include_summary", True)),
            criteria.get("library_id"),
            context.server,
        )
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
    context.server.library.sections()
    return {"user_id": context.user_id, "user": context.user}


async def async_validate_user_context(
    client: PlexExtendedClient,
    user_id: str | int,
) -> dict[str, Any]:
    """Validate a default-user selection through the client's executor lock."""
    return await client._async_run(_validate_user_context, client, user_id)
