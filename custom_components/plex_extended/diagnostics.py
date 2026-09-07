"""Diagnostics support for Plex Extended."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .client import PlexExtendedClient, PlexExtendedError
from .const import (
    CONF_ACCOUNT_TOKEN,
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_MACHINE_IDENTIFIER,
    CONF_SERVER_NAME,
    CONF_SERVER_TOKEN,
)

TO_REDACT = {
    CONF_ACCOUNT_TOKEN,
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_MACHINE_IDENTIFIER,
    CONF_SERVER_NAME,
    CONF_SERVER_TOKEN,
}

FEATURES = [
    "search",
    "query_library",
    "recently_added",
    "recently_watched",
    "continue_watching",
    "on_deck",
    "media_details",
    "list_libraries",
    "list_users",
    "native_llm_tools",
]


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry[PlexExtendedClient],
) -> dict[str, Any]:
    """Return privacy-safe diagnostics for a Plex Extended config entry."""
    result: dict[str, Any] = {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "features": FEATURES,
    }

    base_url = entry.data.get(CONF_BASE_URL)
    if isinstance(base_url, str):
        parsed = urlparse(base_url)
        result["connection"] = {
            "scheme": parsed.scheme or None,
            "secure": parsed.scheme.casefold() == "https",
        }

    client = entry.runtime_data
    if not isinstance(client, PlexExtendedClient):
        result["runtime"] = {"loaded": False}
        return result

    result["runtime"] = {"loaded": True}

    try:
        connection = await client.async_test_connection()
    except PlexExtendedError as err:
        result["server"] = {
            "reachable": False,
            "error_type": type(err).__name__,
        }
    else:
        result["server"] = {
            "reachable": True,
            "version": connection.get("version"),
            "platform": connection.get("platform"),
        }

    try:
        libraries = await client.async_list_libraries()
    except PlexExtendedError as err:
        result["libraries"] = {
            "available": False,
            "error_type": type(err).__name__,
        }
    else:
        # Titles and UUIDs are intentionally omitted: users can name libraries
        # with personal information, while section IDs/types are enough for
        # support diagnostics.
        result["libraries"] = {
            "available": True,
            "count": libraries.get("count", 0),
            "sections": [
                {
                    "id": library.get("id"),
                    "type": library.get("type"),
                }
                for library in libraries.get("libraries", [])
            ],
        }

    return result
