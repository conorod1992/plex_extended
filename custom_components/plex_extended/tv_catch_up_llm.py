"""Native Home Assistant LLM tool for Plex TV catch-up queries."""

from __future__ import annotations

from typing import override

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import LLMContext, ToolInput
from homeassistant.util.json import JsonObjectType

from .client import PlexExtendedClient
from .llm_tools import LLM_LIMIT, PlexTool
from .tv_catch_up import async_tv_catch_up

_WINDOW_DAYS = vol.All(vol.Coerce(int), vol.Range(min=1, max=3650))
_EPISODE_LIMIT = vol.All(vol.Coerce(int), vol.Range(min=1, max=10))


class TvCatchUpPlexTool(PlexTool):
    """Return unwatched/in-progress TV episodes grouped by show."""

    name = "plex_extended__tv_catch_up"
    description = (
        "Return TV episodes the selected/default Plex user still has to watch, grouped by "
        "show and ordered by newest addition. Optionally restrict to episodes added within "
        "a relative or absolute time window. Use this for questions such as what new TV "
        "episodes are waiting, which shows have new unwatched episodes, or what the user "
        "has to catch up on across shows. For detailed progress in one named show, use "
        "watch_status instead."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._user_fields(),
                vol.Optional("library"): cv.string,
                vol.Optional("library_id"): cv.string,
                vol.Optional("since"): vol.All(cv.string, vol.Length(min=1)),
                vol.Optional("before"): vol.All(cv.string, vol.Length(min=1)),
                vol.Optional("within_days"): _WINDOW_DAYS,
                vol.Optional("include_specials", default=False): cv.boolean,
                vol.Optional("include_in_progress", default=True): cv.boolean,
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional("episode_limit", default=5): _EPISODE_LIMIT,
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
            async_tv_catch_up(self._client(data), self._criteria(data))
        )
