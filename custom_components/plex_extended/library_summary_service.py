"""Home Assistant action adapter for aggregate Plex library summaries."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import (
    DEFAULT_FACET_LIMIT,
    DOMAIN,
    LIBRARY_SUMMARY_FACETS,
    MAX_FACET_LIMIT,
    SERVICE_LIBRARY_SUMMARY,
)
from .library_summary import async_library_summary
from .services import QUERY_LIBRARY_SCHEMA, _client_for_call, _criteria, _translate_errors

_EXCLUDED_QUERY_FIELDS = {
    "sort_by",
    "sort_order",
    "limit",
    "include_summary",
    "include_technical",
}


def _field_name(field: object) -> object:
    """Return the underlying name from a Voluptuous marker."""
    return getattr(field, "schema", field)


_SUMMARY_FIELDS = {
    field: validator
    for field, validator in QUERY_LIBRARY_SCHEMA.schema.items()
    if _field_name(field) not in _EXCLUDED_QUERY_FIELDS
}

LIBRARY_SUMMARY_SCHEMA = vol.Schema(
    {
        **_SUMMARY_FIELDS,
        vol.Optional("facets"): vol.All(
            cv.ensure_list,
            [vol.In(LIBRARY_SUMMARY_FACETS)],
        ),
        vol.Optional("facet_limit", default=DEFAULT_FACET_LIMIT): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=MAX_FACET_LIMIT),
        ),
        vol.Optional("include_total_duration", default=False): cv.boolean,
    }
)


async def async_setup_library_summary_service(hass: HomeAssistant) -> None:
    """Register the aggregate library-summary response-data action."""

    async def handle_library_summary(call: ServiceCall) -> ServiceResponse:
        return await _translate_errors(
            async_library_summary(_client_for_call(hass, call), _criteria(call))
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_LIBRARY_SUMMARY,
        handle_library_summary,
        schema=LIBRARY_SUMMARY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
