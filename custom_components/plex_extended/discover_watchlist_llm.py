"""Native Assist tools for Plex Discover and account Watchlist changes."""

from __future__ import annotations

from typing import Any, override

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import LLMContext, ToolInput
from homeassistant.util.json import JsonObjectType

from .client import PlexExtendedClient
from .discover_watchlist import (
    async_add_to_watchlist,
    async_discover_search,
    async_remove_from_watchlist,
)
from .llm_tools import LLM_LIMIT, PlexTool


class DiscoverSearchPlexTool(PlexTool):
    """Search Plex Discover rather than the local server library."""

    name = "plex_extended__discover_search"
    description = (
        "Search Plex Discover for movies or TV shows, including titles not present on the "
        "local Plex server. Returns exact Discover guid values suitable for a later "
        "Watchlist mutation when the user explicitly asks for one."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                vol.Required("query"): vol.All(cv.string, vol.Length(min=1)),
                vol.Optional("media_type"): vol.In(("movie", "show")),
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional("match_local", default=True): cv.boolean,
                vol.Optional("include_summary", default=False): cv.boolean,
            }
        )

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: ToolInput,
        llm_context: LLMContext,
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            async_discover_search(self._client(data), self._criteria(data))
        )


class _WatchlistMutationPlexTool(PlexTool):
    """Base class for exact-GUID account Watchlist mutation tools."""

    def __init__(
        self,
        clients: dict[str, PlexExtendedClient],
        *,
        force_server_selector: bool = False,
    ) -> None:
        self._force_server_selector = force_server_selector
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                vol.Required("guid"): vol.All(cv.string, vol.Length(min=1)),
                vol.Required("title"): vol.All(cv.string, vol.Length(min=1)),
                vol.Optional("media_type"): vol.In(("movie", "show")),
            }
        )

    @override
    def _server_fields(self) -> dict[Any, Any]:
        if self._force_server_selector:
            return {vol.Required("server"): vol.In(list(self._clients))}
        return super()._server_fields()


class AddToWatchlistPlexTool(_WatchlistMutationPlexTool):
    """Add one exact Plex Discover item to the configured account Watchlist."""

    name = "plex_extended__add_to_watchlist"
    description = (
        "Add one exact Plex Discover movie/show to the configured plex.tv account's "
        "Watchlist. Use only after the user explicitly asks to add it and only with the "
        "guid and title returned by discover_search. Never invent, infer, or alter a guid."
    )

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: ToolInput,
        llm_context: LLMContext,
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            async_add_to_watchlist(self._client(data), self._criteria(data))
        )


class RemoveFromWatchlistPlexTool(_WatchlistMutationPlexTool):
    """Remove one exact Plex Discover item from the configured account Watchlist."""

    name = "plex_extended__remove_from_watchlist"
    description = (
        "Remove one exact Plex Discover movie/show from the configured plex.tv account's "
        "Watchlist. Use only after the user explicitly asks to remove it and only with an "
        "exact guid/title pair obtained from Plex Extended data. Never guess the guid."
    )

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: ToolInput,
        llm_context: LLMContext,
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            async_remove_from_watchlist(self._client(data), self._criteria(data))
        )
