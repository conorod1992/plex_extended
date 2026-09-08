"""Native Assist tools for safe Plex playlist mutations."""

from __future__ import annotations

from typing import Any, override

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import LLMContext, ToolInput
from homeassistant.util.json import JsonObjectType

from .client import PlexExtendedClient
from .llm_tools import PlexTool
from .playlist_mutations import (
    async_add_to_playlist,
    async_create_playlist,
    async_remove_from_playlist,
)

_LLM_RATING_KEYS = vol.All(
    cv.ensure_list,
    [vol.All(cv.string, vol.Length(min=1))],
    vol.Length(min=1, max=25),
)


class _PlaylistMutationPlexTool(PlexTool):
    """Base class for playlist-write tools with restricted server exposure."""

    def __init__(
        self,
        clients: dict[str, PlexExtendedClient],
        *,
        force_server_selector: bool = False,
    ) -> None:
        self._force_server_selector = force_server_selector
        super().__init__(clients)

    @override
    def _server_fields(self) -> dict[Any, Any]:
        if self._force_server_selector:
            return {vol.Required("server"): vol.In(list(self._clients))}
        return super()._server_fields()


class CreatePlaylistPlexTool(_PlaylistMutationPlexTool):
    """Create one regular playlist from exact local media IDs."""

    name = "plex_extended__create_playlist"
    description = (
        "Create a regular Plex playlist for the selected/default Plex user from exact "
        "local media rating_key values. Use only when the user explicitly asks to create "
        "a playlist, and only with rating keys returned by Plex Extended read tools. Never "
        "guess media identifiers. Audio, video, and photo media cannot be mixed."
    )

    def __init__(
        self,
        clients: dict[str, PlexExtendedClient],
        *,
        force_server_selector: bool = False,
    ) -> None:
        super().__init__(clients, force_server_selector=force_server_selector)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._user_fields(),
                vol.Required("title"): vol.All(cv.string, vol.Length(min=1)),
                vol.Required("rating_keys"): _LLM_RATING_KEYS,
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
            async_create_playlist(self._client(data), self._criteria(data))
        )


class _ExistingPlaylistMutationPlexTool(_PlaylistMutationPlexTool):
    """Base for exact-ID changes to an existing regular playlist."""

    def __init__(
        self,
        clients: dict[str, PlexExtendedClient],
        *,
        force_server_selector: bool = False,
    ) -> None:
        super().__init__(clients, force_server_selector=force_server_selector)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._user_fields(),
                vol.Required("playlist_rating_key"): vol.All(
                    cv.string, vol.Length(min=1)
                ),
                vol.Required("rating_keys"): _LLM_RATING_KEYS,
            }
        )


class AddToPlaylistPlexTool(_ExistingPlaylistMutationPlexTool):
    """Add exact local media IDs to one regular playlist."""

    name = "plex_extended__add_to_playlist"
    description = (
        "Add local Plex media to one existing regular playlist. Use only after an explicit "
        "user request, with the exact playlist_rating_key from list_playlists and exact "
        "media rating_key values from Plex Extended read tools. Already-present items are "
        "left unchanged; never guess identifiers."
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
            async_add_to_playlist(self._client(data), self._criteria(data))
        )


class RemoveFromPlaylistPlexTool(_ExistingPlaylistMutationPlexTool):
    """Remove exact local media IDs from one regular playlist."""

    name = "plex_extended__remove_from_playlist"
    description = (
        "Remove local Plex media from one existing regular playlist. Use only after an "
        "explicit user request, with the exact playlist_rating_key from list_playlists and "
        "exact media rating_key values from Plex Extended read tools. The operation removes "
        "all occurrences of each requested item and is safe to retry. Never guess IDs."
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
            async_remove_from_playlist(self._client(data), self._criteria(data))
        )
