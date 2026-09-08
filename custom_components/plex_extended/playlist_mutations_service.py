"""Home Assistant actions for safe Plex playlist mutations."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_CONFIG_ENTRY_ID,
    DOMAIN,
    SERVICE_ADD_TO_PLAYLIST,
    SERVICE_CREATE_PLAYLIST,
    SERVICE_REMOVE_FROM_PLAYLIST,
)
from .playlist_mutations import (
    async_add_to_playlist,
    async_create_playlist,
    async_remove_from_playlist,
)
from .services import _client_for_call, _criteria, _translate_errors

_TARGET = {vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string}
_USER = {
    vol.Optional("user"): cv.string,
    vol.Optional("user_id"): cv.string,
}
_RATING_KEYS = vol.All(
    cv.ensure_list,
    [vol.All(cv.string, vol.Length(min=1))],
    vol.Length(min=1, max=50),
)

CREATE_PLAYLIST_SCHEMA = vol.Schema(
    {
        **_TARGET,
        **_USER,
        vol.Required("title"): vol.All(cv.string, vol.Length(min=1)),
        vol.Required("rating_keys"): _RATING_KEYS,
    }
)

PLAYLIST_MUTATION_SCHEMA = vol.Schema(
    {
        **_TARGET,
        **_USER,
        vol.Required("playlist_rating_key"): vol.All(cv.string, vol.Length(min=1)),
        vol.Required("rating_keys"): _RATING_KEYS,
    }
)


async def async_setup_playlist_mutation_services(hass: HomeAssistant) -> None:
    """Register exact-ID regular-playlist mutation actions."""

    async def handle_create_playlist(call: ServiceCall) -> ServiceResponse | None:
        result = await _translate_errors(
            async_create_playlist(_client_for_call(hass, call), _criteria(call))
        )
        return result if call.return_response else None

    async def handle_add_to_playlist(call: ServiceCall) -> ServiceResponse | None:
        result = await _translate_errors(
            async_add_to_playlist(_client_for_call(hass, call), _criteria(call))
        )
        return result if call.return_response else None

    async def handle_remove_from_playlist(call: ServiceCall) -> ServiceResponse | None:
        result = await _translate_errors(
            async_remove_from_playlist(_client_for_call(hass, call), _criteria(call))
        )
        return result if call.return_response else None

    for service, handler, schema in (
        (SERVICE_CREATE_PLAYLIST, handle_create_playlist, CREATE_PLAYLIST_SCHEMA),
        (SERVICE_ADD_TO_PLAYLIST, handle_add_to_playlist, PLAYLIST_MUTATION_SCHEMA),
        (SERVICE_REMOVE_FROM_PLAYLIST, handle_remove_from_playlist, PLAYLIST_MUTATION_SCHEMA),
    ):
        hass.services.async_register(
            DOMAIN,
            service,
            handler,
            schema=schema,
            supports_response=SupportsResponse.OPTIONAL,
        )
