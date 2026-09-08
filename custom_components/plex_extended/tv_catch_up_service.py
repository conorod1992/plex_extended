"""Home Assistant action adapter for Plex TV catch-up queries."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import CONF_CONFIG_ENTRY_ID, DEFAULT_LIMIT, DOMAIN, MAX_LIMIT, SERVICE_TV_CATCH_UP
from .services import _client_for_call, _criteria, _translate_errors
from .tv_catch_up import async_tv_catch_up

_LIMIT = vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_LIMIT))
_WINDOW_DAYS = vol.All(vol.Coerce(int), vol.Range(min=1, max=3650))

TV_CATCH_UP_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
        vol.Optional("library"): cv.string,
        vol.Optional("library_id"): cv.string,
        vol.Optional("user"): cv.string,
        vol.Optional("user_id"): cv.string,
        vol.Optional("since"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("before"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("within_days"): _WINDOW_DAYS,
        vol.Optional("include_specials", default=False): cv.boolean,
        vol.Optional("include_in_progress", default=True): cv.boolean,
        vol.Optional("limit", default=DEFAULT_LIMIT): _LIMIT,
        vol.Optional("episode_limit", default=DEFAULT_LIMIT): _LIMIT,
        vol.Optional("include_summary", default=True): cv.boolean,
    }
)


async def async_setup_tv_catch_up_service(hass: HomeAssistant) -> None:
    """Register the TV catch-up response-data action."""

    async def handle_tv_catch_up(call: ServiceCall) -> ServiceResponse:
        return await _translate_errors(
            async_tv_catch_up(_client_for_call(hass, call), _criteria(call))
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_TV_CATCH_UP,
        handle_tv_catch_up,
        schema=TV_CATCH_UP_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
