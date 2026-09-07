"""Native Home Assistant LLM tool for active Plex streams."""

from __future__ import annotations

from typing import override

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import LLMContext, ToolInput
from homeassistant.util.json import JsonObjectType

from .active_streams import async_active_streams
from .client import PlexExtendedClient
from .const import ACTIVE_STREAM_LOCALITIES, ACTIVE_STREAM_STATES, SEARCH_TYPES
from .llm_tools import LLM_LIMIT, PlexTool


class ActiveStreamsPlexTool(PlexTool):
    """Return active playback sessions from Plex."""

    name = "plex_extended__active_streams"
    description = (
        "Return current Plex playback sessions: who is watching/listening, the media, "
        "player and playback state, progress, local/remote location, source quality, and "
        "whether delivery is direct play, direct stream, or transcode. Use this for "
        "questions about what is playing now or who is currently using Plex."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                vol.Optional("user"): cv.string,
                vol.Optional("media_types"): vol.All(
                    cv.ensure_list,
                    [vol.In(SEARCH_TYPES)],
                ),
                vol.Optional("states"): vol.All(
                    cv.ensure_list,
                    [vol.In(ACTIVE_STREAM_STATES)],
                ),
                vol.Optional("locality", default="any"): vol.In(
                    ACTIVE_STREAM_LOCALITIES
                ),
                vol.Optional("limit", default=25): LLM_LIMIT,
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
            async_active_streams(self._client(data), self._criteria(data))
        )
