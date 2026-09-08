"""Regression tests for runtime Plex auth and connection error propagation."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

from plexapi.exceptions import NotFound, Unauthorized
import pytest
from requests.exceptions import ConnectionError

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"


def _install_homeassistant_stubs() -> None:
    homeassistant = ModuleType("homeassistant")
    config_entries = ModuleType("homeassistant.config_entries")
    core = ModuleType("homeassistant.core")

    class ConfigEntry:
        pass

    class HomeAssistant:
        pass

    config_entries.ConfigEntry = ConfigEntry
    core.HomeAssistant = HomeAssistant
    sys.modules.setdefault("homeassistant", homeassistant)
    sys.modules.setdefault("homeassistant.config_entries", config_entries)
    sys.modules.setdefault("homeassistant.core", core)


def _load_component_module(name: str) -> ModuleType:
    full_name = f"custom_components.plex_extended.{name}"
    existing = sys.modules.get(full_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(full_name, COMPONENT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


_install_homeassistant_stubs()
custom_components = sys.modules.setdefault("custom_components", ModuleType("custom_components"))
custom_components.__path__ = [str(ROOT / "custom_components")]
package = sys.modules.setdefault(
    "custom_components.plex_extended", ModuleType("custom_components.plex_extended")
)
package.__path__ = [str(COMPONENT)]

_load_component_module("const")
client_module = _load_component_module("client")
context_module = _load_component_module("user_context")
related_module = _load_component_module("related_media")

PlexExtendedClient = client_module.PlexExtendedClient
PlexExtendedAuthenticationError = client_module.PlexExtendedAuthenticationError
PlexExtendedConnectionError = client_module.PlexExtendedConnectionError
PlexExtendedError = client_module.PlexExtendedError
async_validate_user_context = context_module.async_validate_user_context
resolve_user_context = context_module.resolve_user_context
async_related_media = related_module.async_related_media


class FakeHass:
    async def async_add_executor_job(self, func):
        return func()


class FakeEntry:
    def __init__(self) -> None:
        self.options = {}
        self.reauth_calls = 0

    def async_start_reauth(self, hass) -> None:
        self.reauth_calls += 1


class FakeLibrary:
    def sections(self):
        return [SimpleNamespace(key="1", title="Movies", type="movie")]


class FakeServer:
    def __init__(self) -> None:
        self.library = FakeLibrary()
        self.accounts = [
            SimpleNamespace(id=1, name="Owner"),
            SimpleNamespace(id=7, name="Conor"),
        ]
        self.fetch_error: Exception | None = None
        self.source = SimpleNamespace(
            ratingKey="10",
            type="movie",
            title="Alien",
            librarySectionID=1,
            librarySectionTitle="Movies",
            viewCount=0,
            hubs=lambda: [],
        )

    def fetchItem(self, rating_key):
        if self.fetch_error is not None:
            raise self.fetch_error
        return self.source

    def systemAccounts(self):
        return list(self.accounts)

    def switchUser(self, name):
        raise KeyError(name)


def _client(server: FakeServer) -> PlexExtendedClient:
    client = object.__new__(PlexExtendedClient)
    client._server = server
    client.hass = FakeHass()
    client.entry = FakeEntry()
    return client


def _run(awaitable_factory, client: PlexExtendedClient):
    async def runner():
        client._lock = asyncio.Lock()
        return await awaitable_factory()

    return asyncio.run(runner())


def test_related_media_unauthorized_starts_reauthentication() -> None:
    server = FakeServer()
    server.fetch_error = Unauthorized("expired token")
    client = _client(server)

    with pytest.raises(PlexExtendedAuthenticationError, match="no longer valid"):
        _run(
            lambda: async_related_media(client, {"rating_key": "10"}),
            client,
        )

    assert client.entry.reauth_calls == 1


def test_related_media_connection_error_remains_connection_error() -> None:
    server = FakeServer()
    server.fetch_error = ConnectionError("offline")
    client = _client(server)

    with pytest.raises(PlexExtendedConnectionError, match="Unable to communicate"):
        _run(
            lambda: async_related_media(client, {"rating_key": "10"}),
            client,
        )

    assert client.entry.reauth_calls == 0


def test_related_hub_unauthorized_starts_reauthentication() -> None:
    server = FakeServer()

    def denied_hubs():
        raise Unauthorized("expired token")

    server.source.hubs = denied_hubs
    client = _client(server)

    with pytest.raises(PlexExtendedAuthenticationError, match="no longer valid"):
        _run(
            lambda: async_related_media(client, {"rating_key": "10"}),
            client,
        )

    assert client.entry.reauth_calls == 1


def test_related_media_not_found_stays_feature_error_without_reauth() -> None:
    server = FakeServer()
    server.fetch_error = NotFound("missing")
    client = _client(server)

    with pytest.raises(PlexExtendedError, match="Plex media not found"):
        _run(
            lambda: async_related_media(client, {"rating_key": "10"}),
            client,
        )

    assert client.entry.reauth_calls == 0


def test_valid_non_owner_switch_denial_stays_permission_error() -> None:
    server = FakeServer()

    def denied_switch(name):
        raise Unauthorized("not permitted")

    server.switchUser = denied_switch
    client = _client(server)

    with pytest.raises(PlexExtendedError, match="must be the server owner"):
        resolve_user_context(client, user_id="7")

    assert client.entry.reauth_calls == 0


def test_expired_auth_during_switch_escapes_for_central_reauth() -> None:
    server = FakeServer()
    account_calls = 0

    def accounts_then_expired():
        nonlocal account_calls
        account_calls += 1
        if account_calls == 1:
            return list(server.accounts)
        raise Unauthorized("expired token")

    def denied_switch(name):
        raise Unauthorized("switch rejected")

    server.systemAccounts = accounts_then_expired
    server.switchUser = denied_switch
    client = _client(server)

    with pytest.raises(Unauthorized, match="expired token"):
        resolve_user_context(client, user_id="7")

    assert account_calls == 2


def test_expired_auth_during_async_user_validation_starts_reauth() -> None:
    server = FakeServer()
    account_calls = 0

    def accounts_then_expired():
        nonlocal account_calls
        account_calls += 1
        if account_calls == 1:
            return list(server.accounts)
        raise Unauthorized("expired token")

    def denied_switch(name):
        raise Unauthorized("switch rejected")

    server.systemAccounts = accounts_then_expired
    server.switchUser = denied_switch
    client = _client(server)

    with pytest.raises(PlexExtendedAuthenticationError, match="no longer valid"):
        _run(lambda: async_validate_user_context(client, "7"), client)

    assert client.entry.reauth_calls == 1
    assert account_calls == 2


def test_switch_user_connection_failure_reaches_central_wrapper() -> None:
    server = FakeServer()

    def offline_switch(name):
        raise ConnectionError("offline")

    server.switchUser = offline_switch
    client = _client(server)

    with pytest.raises(PlexExtendedConnectionError, match="Unable to communicate"):
        _run(lambda: async_validate_user_context(client, "7"), client)

    assert client.entry.reauth_calls == 0
