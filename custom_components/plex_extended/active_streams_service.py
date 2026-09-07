"""Home Assistant action adapter for active Plex streams."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .active_streams import async_active_streams
from .const import (
    ACTIVE_STREAM_LOCALITIES,
    ACTIVE_STREAM_STATES,
    CONF_CONFIG_ENTRY_ID,
    DOMAIN,
    MAX_LIMIT,
    SEARCH_TYPES,
    SERVICE_ACTIVE_STREAMS,
)
from .services import _client_for_call, _criteria, _translate_errors

ACTIVE_STREAMS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
        vol.Optional("user"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("media_types"): vol.All(cv.ensure_list, [vol.In(SEARCH_TYPES)]),
        vol.Optional("states"): vol.All(
            cv.ensure_list,
            [vol.In(ACTIVE_STREAM_STATES)],
        ),
        vol.Optional("locality", default="any"): vol.In(ACTIVE_STREAM_LOCALITIES),
        vol.Optional("limit", default=MAX_LIMIT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_LIMIT)
        ),
    }
)


async def async_setup_active_streams_service(hass: HomeAssistant) -> None:
    """Register the active-streams response-data action."""

    async def handle_active_streams(call: ServiceCall) -> ServiceResponse:
        return await _translate_errors(
            async_active_streams(_client_for_call(hass, call), _criteria(call))
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_ACTIVE_STREAMS,
        handle_active_streams,
        schema=ACTIVE_STREAMS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
