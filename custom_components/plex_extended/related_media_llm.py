"""Native Home Assistant LLM tool for Plex related-media queries."""

from __future__ import annotations

from typing import override

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import LLMContext, ToolInput
from homeassistant.util.json import JsonObjectType

from .client import PlexExtendedClient
from .llm_tools import PlexTool
from .related_media import async_related_media

_HUB_LIMIT = vol.All(vol.Coerce(int), vol.Range(min=1, max=10))
_ITEM_LIMIT = vol.All(vol.Coerce(int), vol.Range(min=1, max=10))


class RelatedMediaPlexTool(PlexTool):
    """Return Plex-native related hubs for one local movie/show."""

    name = "plex_extended__related_media"
    description = (
        "Return Plex's own related/recommendation hubs for one exact local movie or TV "
        "show rating_key, preserving categories such as related titles or shared people. "
        "Use search/query_library first when the rating_key is not already known. Results "
        "contain only local Plex media; never invent a rating_key."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._library_fields(),
                **self._user_fields(),
                vol.Required("rating_key"): vol.All(cv.string, vol.Length(min=1)),
                vol.Optional("hub_limit", default=6): _HUB_LIMIT,
                vol.Optional("item_limit", default=5): _ITEM_LIMIT,
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
            async_related_media(self._client(data), self._criteria(data))
        )
