"""Home Assistant config-entry lifecycle tests for Plex Extended."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.plex_extended.client import PlexExtendedClient
from custom_components.plex_extended.const import (
    DOMAIN,
    SERVICE_RELATED_MEDIA,
    SERVICE_SEARCH,
)


async def test_setup_and_unload_release_runtime_state(
    hass: HomeAssistant,
    entry_factory,
    mock_connect,
) -> None:
    """A real HA config entry should load, expose actions, and cleanly unload."""
    entry = entry_factory()

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, PlexExtendedClient)
    assert hass.services.has_service(DOMAIN, SERVICE_SEARCH)
    assert hass.services.has_service(DOMAIN, SERVICE_RELATED_MEDIA)

    client = entry.runtime_data
    client._server = object()
    client._plex_extended_user_servers = {7: object(), 8: object()}

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert client._server is None
    assert client._plex_extended_user_servers == {}
