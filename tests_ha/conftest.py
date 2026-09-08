"""Fixtures for Plex Extended tests that run against real Home Assistant."""

from __future__ import annotations

from collections.abc import Callable, Generator
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plex_extended.const import (
    CONF_BASE_URL,
    CONF_MACHINE_IDENTIFIER,
    CONF_SERVER_NAME,
    CONF_SERVER_TOKEN,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations) -> None:
    """Allow Home Assistant's loader to discover this repository's custom integration."""


@pytest.fixture
def mock_connect() -> Generator[AsyncMock]:
    """Prevent integration tests from opening a real Plex connection."""
    with patch(
        "custom_components.plex_extended.client.PlexExtendedClient.async_connect",
        new_callable=AsyncMock,
    ) as mocked:
        yield mocked


@pytest.fixture
def entry_factory(hass: HomeAssistant) -> Callable[..., MockConfigEntry]:
    """Create Plex Extended config entries with realistic stored data."""

    def factory(
        *,
        title: str = "Plex A",
        machine_identifier: str = "machine-a",
        token: str = "server-token-a",
        options: dict | None = None,
    ) -> MockConfigEntry:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=title,
            unique_id=machine_identifier,
            data={
                CONF_BASE_URL: f"http://{machine_identifier}.example:32400",
                CONF_SERVER_TOKEN: token,
                CONF_MACHINE_IDENTIFIER: machine_identifier,
                CONF_SERVER_NAME: title,
            },
            options=options or {},
        )
        entry.add_to_hass(hass)
        return entry

    return factory
