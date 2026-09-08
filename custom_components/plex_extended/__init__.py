"""Plex Extended integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType

from .active_streams_service import async_setup_active_streams_service
from .client import (
    PlexExtendedAuthenticationError,
    PlexExtendedClient,
    PlexExtendedConnectionError,
)
from .library_summary_service import async_setup_library_summary_service
from .services import async_setup_services

PlexExtendedConfigEntry = ConfigEntry[PlexExtendedClient]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Plex Extended and register its actions."""
    await async_setup_services(hass)
    await async_setup_active_streams_service(hass)
    await async_setup_library_summary_service(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: PlexExtendedConfigEntry
) -> bool:
    """Set up a Plex Extended config entry."""
    client = PlexExtendedClient(hass, entry)
    try:
        await client.async_connect()
    except PlexExtendedAuthenticationError as err:
        raise ConfigEntryAuthFailed("Plex authorization is invalid") from err
    except PlexExtendedConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = client
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: PlexExtendedConfigEntry
) -> bool:
    """Unload a Plex Extended config entry."""
    # PlexAPI has no persistent background task in Plex Extended v1. The
    # runtime client becomes unreachable when Home Assistant unloads the entry.
    return True
