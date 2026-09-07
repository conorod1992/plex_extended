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
    QUERY_HDR_STATES,
    QUERY_MEDIA_TYPES,
    QUERY_SORT_FIELDS,
    QUERY_SORT_ORDERS,
    QUERY_WATCH_STATES,
    RECENT_TV_GROUPINGS,
    SEARCH_TYPES,
    SERVICE_CONTINUE_WATCHING,
    SERVICE_LIST_LIBRARIES,
    SERVICE_LIST_USERS,
    SERVICE_MEDIA_DETAILS,
    SERVICE_ON_DECK,
    SERVICE_QUERY_LIBRARY,
    SERVICE_RECENTLY_ADDED,
    SERVICE_RECENTLY_WATCHED,
    SERVICE_SEARCH,
    SERVICE_TEST_CONNECTION,
    SERVICE_WATCH_STATUS,
)
from .library_query import async_query_library
from .recent_media import async_recently_added, async_recently_watched
from .user_context import (
    async_continue_watching_for_context,
    async_media_details_for_context,
    async_on_deck_for_context,
    async_search_for_context,
)
from .viewing_progress import async_watch_status

LIMIT_SCHEMA = vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_LIMIT))
MEDIA_TYPES_SCHEMA = vol.All(cv.ensure_list, [vol.In(SEARCH_TYPES)])
TEXT_LIST_SCHEMA = vol.All(
    cv.ensure_list,
    [vol.All(cv.string, vol.Length(min=1))],
)
YEAR_SCHEMA = vol.All(vol.Coerce(int), vol.Range(min=0, max=9999))
RATING_SCHEMA = vol.All(vol.Coerce(float), vol.Range(min=0, max=10))
DURATION_SCHEMA = vol.All(vol.Coerce(float), vol.Range(min=0))
WINDOW_DAYS_SCHEMA = vol.All(vol.Coerce(int), vol.Range(min=1, max=3650))

TARGET_SCHEMA = {
    vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
}
LIBRARY_SCHEMA = {
    vol.Optional("library"): cv.string,
    vol.Optional("library_id"): cv.string,
}
USER_SCHEMA = {
    vol.Optional("user"): cv.string,
    vol.Optional("user_id"): cv.string,
}
WINDOW_SCHEMA = {
    vol.Optional("since"): vol.All(cv.string, vol.Length(min=1)),
    vol.Optional("before"): vol.All(cv.string, vol.Length(min=1)),
    vol.Optional("within_days"): WINDOW_DAYS_SCHEMA,
}

SEARCH_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        **LIBRARY_SCHEMA,
        **USER_SCHEMA,
        vol.Required("query"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("search_types", default=DEFAULT_SEARCH_TYPES): MEDIA_TYPES_SCHEMA,
        vol.Optional("limit", default=DEFAULT_LIMIT): LIMIT_SCHEMA,
        vol.Optional("include_summary", default=True): cv.boolean,
        vol.Optional("include_technical", default=False): cv.boolean,
    }
)

QUERY_LIBRARY_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        **LIBRARY_SCHEMA,
        **USER_SCHEMA,
        vol.Required("media_type"): vol.In(QUERY_MEDIA_TYPES),
        vol.Optional("title"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("genres"): TEXT_LIST_SCHEMA,
        vol.Optional("genres_all"): TEXT_LIST_SCHEMA,
        vol.Optional("actors"): TEXT_LIST_SCHEMA,
        vol.Optional("directors"): TEXT_LIST_SCHEMA,
        vol.Optional("collections"): TEXT_LIST_SCHEMA,
        vol.Optional("content_ratings"): TEXT_LIST_SCHEMA,
        vol.Optional("studios"): TEXT_LIST_SCHEMA,
        vol.Optional("year"): YEAR_SCHEMA,
        vol.Optional("year_min"): YEAR_SCHEMA,
        vol.Optional("year_max"): YEAR_SCHEMA,
        vol.Optional("decade"): YEAR_SCHEMA,
        vol.Optional("watched_state", default="any"): vol.In(QUERY_WATCH_STATES),
        vol.Optional("resolutions"): TEXT_LIST_SCHEMA,
        vol.Optional("hdr", default="any"): vol.In(QUERY_HDR_STATES),
        vol.Optional("critic_rating_min"): RATING_SCHEMA,
        vol.Optional("critic_rating_max"): RATING_SCHEMA,
        vol.Optional("audience_rating_min"): RATING_SCHEMA,
        vol.Optional("audience_rating_max"): RATING_SCHEMA,
        vol.Optional("user_rating_min"): RATING_SCHEMA,
        vol.Optional("user_rating_max"): RATING_SCHEMA,
        vol.Optional("duration_min_minutes"): DURATION_SCHEMA,
        vol.Optional("duration_max_minutes"): DURATION_SCHEMA,
        vol.Optional("added_after"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("added_before"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("last_viewed_after"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("last_viewed_before"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("sort_by"): vol.In(QUERY_SORT_FIELDS),
        vol.Optional("sort_order"): vol.In(QUERY_SORT_ORDERS),
        vol.Optional("limit", default=DEFAULT_LIMIT): LIMIT_SCHEMA,
        vol.Optional("include_summary", default=True): cv.boolean,
        vol.Optional("include_technical", default=False): cv.boolean,
    }
)

WATCH_STATUS_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        **LIBRARY_SCHEMA,
        **USER_SCHEMA,
        vol.Optional("rating_key"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("title"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("year"): YEAR_SCHEMA,
        vol.Optional("include_specials", default=False): cv.boolean,
        vol.Optional("include_seasons", default=True): cv.boolean,
        vol.Optional("include_summary", default=True): cv.boolean,
    }
)

RECENT_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        **LIBRARY_SCHEMA,
        **USER_SCHEMA,
        **WINDOW_SCHEMA,
        vol.Optional("limit", default=DEFAULT_LIMIT): LIMIT_SCHEMA,
        vol.Optional("media_types"): MEDIA_TYPES_SCHEMA,
        vol.Optional("group_tv_by", default="none"): vol.In(RECENT_TV_GROUPINGS),
        vol.Optional("include_summary", default=True): cv.boolean,
    }
)

HISTORY_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        **LIBRARY_SCHEMA,
        **USER_SCHEMA,
        **WINDOW_SCHEMA,
        vol.Optional("limit", default=DEFAULT_LIMIT): LIMIT_SCHEMA,
        vol.Optional("media_types"): MEDIA_TYPES_SCHEMA,
        vol.Optional("include_summary", default=True): cv.boolean,
    }
)

BROWSE_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        **LIBRARY_SCHEMA,
        **USER_SCHEMA,
        vol.Optional("limit", default=DEFAULT_LIMIT): LIMIT_SCHEMA,
        vol.Optional("include_summary", default=True): cv.boolean,
    }
)

DETAILS_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        **USER_SCHEMA,
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


def _criteria(call: ServiceCall) -> dict[str, Any]:
    """Return service data without Home Assistant-only target metadata."""
    return {
        key: value
        for key, value in call.data.items()
        if key != CONF_CONFIG_ENTRY_ID
    }


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
        return await _translate_errors(
            async_search_for_context(_client_for_call(hass, call), _criteria(call))
        )

    async def handle_query_library(call: ServiceCall) -> ServiceResponse:
        return await _translate_errors(
            async_query_library(_client_for_call(hass, call), _criteria(call))
        )

    async def handle_watch_status(call: ServiceCall) -> ServiceResponse:
        return await _translate_errors(
            async_watch_status(_client_for_call(hass, call), _criteria(call))
        )

    async def handle_recently_added(call: ServiceCall) -> ServiceResponse:
        return await _translate_errors(
            async_recently_added(_client_for_call(hass, call), _criteria(call))
        )

    async def handle_recently_watched(call: ServiceCall) -> ServiceResponse:
        return await _translate_errors(
            async_recently_watched(_client_for_call(hass, call), _criteria(call))
        )

    async def handle_continue_watching(call: ServiceCall) -> ServiceResponse:
        return await _translate_errors(
            async_continue_watching_for_context(
                _client_for_call(hass, call), _criteria(call)
            )
        )

    async def handle_on_deck(call: ServiceCall) -> ServiceResponse:
        return await _translate_errors(
            async_on_deck_for_context(_client_for_call(hass, call), _criteria(call))
        )

    async def handle_media_details(call: ServiceCall) -> ServiceResponse:
        return await _translate_errors(
            async_media_details_for_context(
                _client_for_call(hass, call), _criteria(call)
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
        (SERVICE_QUERY_LIBRARY, handle_query_library, QUERY_LIBRARY_SCHEMA),
        (SERVICE_WATCH_STATUS, handle_watch_status, WATCH_STATUS_SCHEMA),
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
