"""Native Home Assistant LLM tool for aggregate Plex library summaries."""

from __future__ import annotations

from typing import override

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import LLMContext, ToolInput
from homeassistant.util.json import JsonObjectType

from .client import PlexExtendedClient
from .const import DEFAULT_FACET_LIMIT, LIBRARY_SUMMARY_FACETS
from .library_summary import async_library_summary
from .llm_tools import QueryLibraryPlexTool

_EXCLUDED_QUERY_FIELDS = {
    "sort_by",
    "sort_order",
    "limit",
    "include_summary",
}
_LLM_MAX_FACET_LIMIT = 25


def _field_name(field: object) -> object:
    """Return the underlying name from a Voluptuous marker."""
    return getattr(field, "schema", field)


class LibrarySummaryPlexTool(QueryLibraryPlexTool):
    """Count and facet Plex media using the structured library-query filters."""

    name = "plex_extended__library_summary"
    description = (
        "Return an exact aggregate count for Plex media matching structured library "
        "criteria, optionally with compact facet breakdowns or total duration. Use this "
        "instead of query_library when the user asks how many items match, how the library "
        "is distributed by genre/year/decade/resolution/watch state/content rating/studio/"
        "collection, or for the total runtime of matching media. Viewing-state criteria use "
        "the configured default Plex user unless user or user_id explicitly overrides it."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        fields = {
            field: validator
            for field, validator in self.parameters.schema.items()
            if _field_name(field) not in _EXCLUDED_QUERY_FIELDS
        }
        self.parameters = vol.Schema(
            {
                **fields,
                vol.Optional("facets"): vol.All(
                    cv.ensure_list,
                    [vol.In(LIBRARY_SUMMARY_FACETS)],
                ),
                vol.Optional("facet_limit", default=DEFAULT_FACET_LIMIT): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, max=_LLM_MAX_FACET_LIMIT),
                ),
                vol.Optional("include_total_duration", default=False): cv.boolean,
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
            async_library_summary(self._client(data), self._criteria(data))
        )
