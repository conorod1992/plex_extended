"""Home Assistant actions for Plex Discover and Watchlist mutations."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_CONFIG_ENTRY_ID,
    DEFAULT_LIMIT,
    DOMAIN,
    MAX_LIMIT,
    SERVICE_ADD_TO_WATCHLIST,
    SERVICE_DISCOVER_SEARCH,
    SERVICE_REMOVE_FROM_WATCHLIST,
)
from .discover_watchlist import (
    async_add_to_watchlist,
    async_discover_search,
    async_remove_from_watchlist,
)
from .services import _client_for_call, _criteria, _translate_errors

_LIMIT = vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_LIMIT))
_TARGET = {vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string}

DISCOVER_SEARCH_SCHEMA = vol.Schema(
    {
        **_TARGET,
        vol.Required("query"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("media_type"): vol.In(("movie", "show")),
        vol.Optional("limit", default=DEFAULT_LIMIT): _LIMIT,
        vol.Optional("match_local", default=False): cv.boolean,
        vol.Optional("include_summary", default=True): cv.boolean,
    }
)

WATCHLIST_MUTATION_SCHEMA = vol.Schema(
    {
        **_TARGET,
        vol.Required("guid"): vol.All(cv.string, vol.Length(min=1)),
        vol.Required("title"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("media_type"): vol.In(("movie", "show")),
    }
)


async def async_setup_discover_watchlist_services(hass: HomeAssistant) -> None:
    """Register Discover search and exact-GUID Watchlist mutation actions."""

    async def handle_discover_search(call: ServiceCall) -> ServiceResponse:
        return await _translate_errors(
            async_discover_search(_client_for_call(hass, call), _criteria(call))
        )

    async def handle_add_to_watchlist(call: ServiceCall) -> ServiceResponse | None:
        result = await _translate_errors(
            async_add_to_watchlist(_client_for_call(hass, call), _criteria(call))
        )
        return result if call.return_response else None

    async def handle_remove_from_watchlist(call: ServiceCall) -> ServiceResponse | None:
        result = await _translate_errors(
            async_remove_from_watchlist(_client_for_call(hass, call), _criteria(call))
        )
        return result if call.return_response else None

    hass.services.async_register(
        DOMAIN,
        SERVICE_DISCOVER_SEARCH,
        handle_discover_search,
        schema=DISCOVER_SEARCH_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_TO_WATCHLIST,
        handle_add_to_watchlist,
        schema=WATCHLIST_MUTATION_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_FROM_WATCHLIST,
        handle_remove_from_watchlist,
        schema=WATCHLIST_MUTATION_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
