"""Home Assistant action adapter for Plex related-media queries."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import CONF_CONFIG_ENTRY_ID, DOMAIN, SERVICE_RELATED_MEDIA
from .related_media import async_related_media
from .services import _client_for_call, _criteria, _translate_errors

_HUB_LIMIT = vol.All(vol.Coerce(int), vol.Range(min=1, max=20))
_ITEM_LIMIT = vol.All(vol.Coerce(int), vol.Range(min=1, max=20))

RELATED_MEDIA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
        vol.Required("rating_key"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("library"): cv.string,
        vol.Optional("library_id"): cv.string,
        vol.Optional("user"): cv.string,
        vol.Optional("user_id"): cv.string,
        vol.Optional("hub_limit", default=10): _HUB_LIMIT,
        vol.Optional("item_limit", default=10): _ITEM_LIMIT,
        vol.Optional("include_summary", default=True): cv.boolean,
    }
)


async def async_setup_related_media_service(hass: HomeAssistant) -> None:
    """Register the related-media response-data action."""

    async def handle_related_media(call: ServiceCall) -> ServiceResponse:
        return await _translate_errors(
            async_related_media(_client_for_call(hass, call), _criteria(call))
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_RELATED_MEDIA,
        handle_related_media,
        schema=RELATED_MEDIA_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
