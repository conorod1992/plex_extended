"""Native Home Assistant LLM tools for Plex Extended."""

from __future__ import annotations

from typing import Any, override

import voluptuous as vol

from homeassistant.components.llm import LLMTools
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import LLM_API_ASSIST, LLMContext, Tool, ToolInput
from homeassistant.util.json import JsonObjectType

from .client import PlexExtendedAuthenticationError, PlexExtendedClient, PlexExtendedError
from .const import DEFAULT_SEARCH_TYPES, DOMAIN, SEARCH_TYPES

LLM_LIMIT = vol.All(vol.Coerce(int), vol.Range(min=1, max=25))
LLM_TYPES = vol.All(cv.ensure_list, [vol.In(SEARCH_TYPES)])


class PlexTool(Tool):
    """Base class for Plex Extended LLM tools."""

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        """Initialize a Plex tool."""
        self._clients = clients

    def _server_fields(self) -> dict[Any, Any]:
        """Return a server selector only when multiple servers are loaded."""
        if len(self._clients) <= 1:
            return {}
        return {vol.Required("server"): vol.In(list(self._clients))}

    def _client(self, data: dict[str, Any]) -> PlexExtendedClient:
        """Resolve the client selected by the LLM."""
        if len(self._clients) == 1:
            return next(iter(self._clients.values()))
        server = data.get("server")
        if not server or server not in self._clients:
            raise HomeAssistantError("A Plex server must be selected")
        return self._clients[server]

    async def _call(self, awaitable: Any) -> JsonObjectType:
        """Translate client errors to Home Assistant tool errors."""
        try:
            return await awaitable
        except PlexExtendedAuthenticationError as err:
            raise HomeAssistantError(
                "Plex authorization failed; Home Assistant has requested reauthentication"
            ) from err
        except PlexExtendedError as err:
            raise HomeAssistantError(str(err)) from err


class SearchPlexTool(PlexTool):
    """Search Plex libraries."""

    name = "plex_extended__search"
    description = "Search the user's Plex libraries for media titles."

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                vol.Required("query"): vol.All(cv.string, vol.Length(min=1)),
                vol.Optional("search_types", default=DEFAULT_SEARCH_TYPES): LLM_TYPES,
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional("library"): cv.string,
                vol.Optional("include_summary", default=True): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            self._client(data).async_search(
                data["query"],
                data.get("search_types"),
                data.get("limit", 10),
                data.get("library"),
                data.get("include_summary", True),
                False,
            )
        )


class RecentlyAddedPlexTool(PlexTool):
    """Return recently added Plex media."""

    name = "plex_extended__recently_added"
    description = "Return recently added items from Plex, optionally filtered by library or media type."

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional("library"): cv.string,
                vol.Optional("media_types"): LLM_TYPES,
                vol.Optional("include_summary", default=True): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            self._client(data).async_recently_added(
                data.get("limit", 10),
                data.get("library"),
                data.get("media_types"),
                data.get("include_summary", True),
            )
        )


class RecentlyWatchedPlexTool(PlexTool):
    """Return Plex watch history."""

    name = "plex_extended__recently_watched"
    description = "Return recent Plex watch history, optionally filtered by Plex user, library, or media type."

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional("library"): cv.string,
                vol.Optional("user"): cv.string,
                vol.Optional("media_types"): LLM_TYPES,
                vol.Optional("include_summary", default=True): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            self._client(data).async_recently_watched(
                data.get("limit", 10),
                data.get("library"),
                data.get("user"),
                data.get("media_types"),
                data.get("include_summary", True),
            )
        )


class ContinueWatchingPlexTool(PlexTool):
    """Return Continue Watching items."""

    name = "plex_extended__continue_watching"
    description = "Return the user's Plex Continue Watching items."

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional("library"): cv.string,
                vol.Optional("include_summary", default=True): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            self._client(data).async_continue_watching(
                data.get("limit", 10),
                data.get("library"),
                data.get("include_summary", True),
            )
        )


class OnDeckPlexTool(PlexTool):
    """Return Plex On Deck items."""

    name = "plex_extended__on_deck"
    description = "Return Plex On Deck items."

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional("library"): cv.string,
                vol.Optional("include_summary", default=True): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            self._client(data).async_on_deck(
                data.get("limit", 10),
                data.get("library"),
                data.get("include_summary", True),
            )
        )


class MediaDetailsPlexTool(PlexTool):
    """Return metadata for a known Plex item."""

    name = "plex_extended__media_details"
    description = "Get detailed metadata for a Plex item using the rating_key returned by another Plex tool."

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                vol.Required("rating_key"): cv.string,
                vol.Optional("include_technical", default=False): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            self._client(data).async_media_details(
                data["rating_key"], data.get("include_technical", False)
            )
        )


class ListLibrariesPlexTool(PlexTool):
    """List Plex libraries."""

    name = "plex_extended__list_libraries"
    description = "List available Plex library names and media types."

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema({**self._server_fields()})

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(self._client(data).async_list_libraries())


class ListUsersPlexTool(PlexTool):
    """List Plex users."""

    name = "plex_extended__list_users"
    description = "List Plex users that can be used to filter watch history."

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema({**self._server_fields()})

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(self._client(data).async_list_users())


def _loaded_clients(hass: HomeAssistant) -> dict[str, PlexExtendedClient]:
    """Return loaded Plex clients with unambiguous display names."""
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and isinstance(entry.runtime_data, PlexExtendedClient)
    ]
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.title] = counts.get(entry.title, 0) + 1

    result: dict[str, PlexExtendedClient] = {}
    for entry in entries:
        label = (
            entry.title
            if counts[entry.title] == 1
            else f"{entry.title} ({entry.entry_id[:8]})"
        )
        result[label] = entry.runtime_data
    return result


@callback
def async_get_tools(
    hass: HomeAssistant, llm_context: LLMContext, api_id: str
) -> LLMTools | None:
    """Contribute Plex tools to Home Assistant's built-in Assist LLM API."""
    if api_id != LLM_API_ASSIST:
        return None

    clients = _loaded_clients(hass)
    if not clients:
        return None

    return LLMTools(
        tools=[
            SearchPlexTool(clients),
            RecentlyAddedPlexTool(clients),
            RecentlyWatchedPlexTool(clients),
            ContinueWatchingPlexTool(clients),
            OnDeckPlexTool(clients),
            MediaDetailsPlexTool(clients),
            ListLibrariesPlexTool(clients),
            ListUsersPlexTool(clients),
        ],
        prompt=(
            "Use Plex Extended tools for questions about the user's Plex library, "
            "watch history, recently added media, Continue Watching, or On Deck. "
            "Search results are limited to media actually present in the configured Plex library."
        ),
    )
