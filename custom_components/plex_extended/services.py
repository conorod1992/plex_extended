"""Home Assistant actions for Plex Extended."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .client import PlexExtendedAuthenticationError, PlexExtendedClient, PlexExtendedError
from .const import (
    CONF_CONFIG_ENTRY_ID,
    DEFAULT_LIMIT,
    DEFAULT_SEARCH_TYPES,
    DOMAIN,
    MAX_LIMIT,
    SEARCH_TYPES,
    SERVICE_CONTINUE_WATCHING,
    SERVICE_LIST_LIBRARIES,
    SERVICE_LIST_USERS,
    SERVICE_MEDIA_DETAILS,
    SERVICE_ON_DECK,
    SERVICE_RECENTLY_ADDED,
    SERVICE_RECENTLY_WATCHED,
    SERVICE_SEARCH,
    SERVICE_TEST_CONNECTION,
)

LIMIT_SCHEMA = vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_LIMIT))
MEDIA_TYPES_SCHEMA = vol.All(cv.ensure_list, [vol.In(SEARCH_TYPES)])

TARGET_SCHEMA = {
    vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
}
LIBRARY_SCHEMA = {
    vol.Optional("library"): cv.string,
    vol.Optional("library_id"): cv.string,
}

SEARCH_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        **LIBRARY_SCHEMA,
        vol.Required("query"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("search_types", default=DEFAULT_SEARCH_TYPES): MEDIA_TYPES_SCHEMA,
        vol.Optional("limit", default=DEFAULT_LIMIT): LIMIT_SCHEMA,
        vol.Optional("include_summary", default=True): cv.boolean,
        vol.Optional("include_technical", default=False): cv.boolean,
    }
)

RECENT_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        **LIBRARY_SCHEMA,
        vol.Optional("limit", default=DEFAULT_LIMIT): LIMIT_SCHEMA,
        vol.Optional("media_types"): MEDIA_TYPES_SCHEMA,
        vol.Optional("include_summary", default=True): cv.boolean,
    }
)

HISTORY_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        **LIBRARY_SCHEMA,
        vol.Optional("limit", default=DEFAULT_LIMIT): LIMIT_SCHEMA,
        vol.Optional("user"): cv.string,
        vol.Optional("user_id"): cv.string,
        vol.Optional("media_types"): MEDIA_TYPES_SCHEMA,
        vol.Optional("include_summary", default=True): cv.boolean,
    }
)

BROWSE_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        **LIBRARY_SCHEMA,
        vol.Optional("limit", default=DEFAULT_LIMIT): LIMIT_SCHEMA,
        vol.Optional("include_summary", default=True): cv.boolean,
    }
)

DETAILS_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        vol.Required("rating_key"): cv.string,
        vol.Optional("include_technical", default=True): cv.boolean,
    }
)

TARGET_ONLY_SCHEMA = vol.Schema(TARGET_SCHEMA)


def _resolve_entry(hass: HomeAssistant, data: dict[str, Any]) -> ConfigEntry:
    """Resolve the target config entry, defaulting only when unambiguous."""
    requested = data.get(CONF_CONFIG_ENTRY_ID)
    if requested:
        entry = hass.config_entries.async_get_entry(requested)
        if entry is None or entry.domain != DOMAIN:
            raise HomeAssistantError("The selected Plex Extended server was not found")
        if entry.state is not ConfigEntryState.LOADED:
            raise HomeAssistantError("The selected Plex Extended server is not loaded")
        return entry

    loaded = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if not loaded:
        raise HomeAssistantError("No loaded Plex Extended server is available")
    if len(loaded) > 1:
        raise HomeAssistantError(
            "Multiple Plex Extended servers are configured; select a server"
        )
    return loaded[0]


def _client_for_call(hass: HomeAssistant, call: ServiceCall) -> PlexExtendedClient:
    """Return the target runtime client."""
    entry = _resolve_entry(hass, call.data)
    client = entry.runtime_data
    if not isinstance(client, PlexExtendedClient):
        raise HomeAssistantError("Plex Extended is not ready")
    return client


async def _translate_errors(awaitable: Any) -> ServiceResponse:
    """Translate integration errors into Home Assistant action errors."""
    try:
        return await awaitable
    except PlexExtendedAuthenticationError as err:
        raise HomeAssistantError(
            "Plex authorization failed. Reauthentication has been requested."
        ) from err
    except PlexExtendedError as err:
        raise HomeAssistantError(str(err)) from err


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register Plex Extended response-data actions."""

    async def handle_search(call: ServiceCall) -> ServiceResponse:
        client = _client_for_call(hass, call)
        return await _translate_errors(
            client.async_search(
                call.data["query"],
                call.data.get("search_types"),
                call.data.get("limit", DEFAULT_LIMIT),
                call.data.get("library"),
                call.data.get("include_summary", True),
                call.data.get("include_technical", False),
                call.data.get("library_id"),
            )
        )

    async def handle_recently_added(call: ServiceCall) -> ServiceResponse:
        client = _client_for_call(hass, call)
        return await _translate_errors(
            client.async_recently_added(
                call.data.get("limit", DEFAULT_LIMIT),
                call.data.get("library"),
                call.data.get("media_types"),
                call.data.get("include_summary", True),
                call.data.get("library_id"),
            )
        )

    async def handle_recently_watched(call: ServiceCall) -> ServiceResponse:
        client = _client_for_call(hass, call)
        return await _translate_errors(
            client.async_recently_watched(
                call.data.get("limit", DEFAULT_LIMIT),
                call.data.get("library"),
                call.data.get("user"),
                call.data.get("media_types"),
                call.data.get("include_summary", True),
                call.data.get("library_id"),
                call.data.get("user_id"),
            )
        )

    async def handle_continue_watching(call: ServiceCall) -> ServiceResponse:
        client = _client_for_call(hass, call)
        return await _translate_errors(
            client.async_continue_watching(
                call.data.get("limit", DEFAULT_LIMIT),
                call.data.get("library"),
                call.data.get("include_summary", True),
                call.data.get("library_id"),
            )
        )

    async def handle_on_deck(call: ServiceCall) -> ServiceResponse:
        client = _client_for_call(hass, call)
        return await _translate_errors(
            client.async_on_deck(
                call.data.get("limit", DEFAULT_LIMIT),
                call.data.get("library"),
                call.data.get("include_summary", True),
                call.data.get("library_id"),
            )
        )

    async def handle_media_details(call: ServiceCall) -> ServiceResponse:
        client = _client_for_call(hass, call)
        return await _translate_errors(
            client.async_media_details(
                call.data["rating_key"],
                call.data.get("include_technical", True),
            )
        )

    async def handle_list_libraries(call: ServiceCall) -> ServiceResponse:
        return await _translate_errors(
            _client_for_call(hass, call).async_list_libraries()
        )

    async def handle_list_users(call: ServiceCall) -> ServiceResponse:
        return await _translate_errors(_client_for_call(hass, call).async_list_users())

    async def handle_test_connection(call: ServiceCall) -> ServiceResponse:
        return await _translate_errors(
            _client_for_call(hass, call).async_test_connection()
        )

    registrations = (
        (SERVICE_SEARCH, handle_search, SEARCH_SCHEMA),
        (SERVICE_RECENTLY_ADDED, handle_recently_added, RECENT_SCHEMA),
        (SERVICE_RECENTLY_WATCHED, handle_recently_watched, HISTORY_SCHEMA),
        (SERVICE_CONTINUE_WATCHING, handle_continue_watching, BROWSE_SCHEMA),
        (SERVICE_ON_DECK, handle_on_deck, BROWSE_SCHEMA),
        (SERVICE_MEDIA_DETAILS, handle_media_details, DETAILS_SCHEMA),
        (SERVICE_LIST_LIBRARIES, handle_list_libraries, TARGET_ONLY_SCHEMA),
        (SERVICE_LIST_USERS, handle_list_users, TARGET_ONLY_SCHEMA),
        (SERVICE_TEST_CONNECTION, handle_test_connection, TARGET_ONLY_SCHEMA),
    )
    for service, handler, schema in registrations:
        hass.services.async_register(
            DOMAIN,
            service,
            handler,
            schema=schema,
            supports_response=SupportsResponse.ONLY,
        )
