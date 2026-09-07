"""Config flow for Plex Extended."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, override

from aiohttp import web_response
from plexapi.exceptions import Unauthorized
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer
from plexauth import PlexAuth
from requests.exceptions import RequestException
import voluptuous as vol

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, http
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import PlexExtendedClient, PlexExtendedError
from .const import (
    AUTH_CALLBACK_NAME,
    AUTH_CALLBACK_PATH,
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_DEFAULT_USER_ID,
    CONF_MACHINE_IDENTIFIER,
    CONF_SERVER_NAME,
    CONF_SERVER_TOKEN,
    DOMAIN,
    HEADER_FRONTEND_BASE,
    X_PLEX_DEVICE_NAME,
    X_PLEX_PLATFORM,
    X_PLEX_PRODUCT,
    X_PLEX_VERSION,
)
from .user_context import async_validate_user_context


def _provides_server(resource: Any) -> bool:
    """Return whether a MyPlex resource provides a server."""
    provides = getattr(resource, "provides", [])
    if isinstance(provides, str):
        provides = [value.strip() for value in provides.split(",")]
    return "server" in provides


def _discover_servers(token: str) -> list[Any]:
    """Discover Plex servers associated with an account token."""
    account = MyPlexAccount(token=token)
    return [resource for resource in account.resources() if _provides_server(resource)]


def _connect_resource(resource: Any) -> dict[str, Any]:
    """Connect to a MyPlex server resource and return config-entry data."""
    server = resource.connect(timeout=10)
    return {
        CONF_BASE_URL: str(server._baseurl),  # PlexAPI exposes no public base URL accessor.
        CONF_SERVER_TOKEN: str(resource.accessToken),
        CONF_MACHINE_IDENTIFIER: str(server.machineIdentifier),
        CONF_SERVER_NAME: str(server.friendlyName),
    }


def _connect_manual(base_url: str, token: str) -> dict[str, Any]:
    """Validate manual Plex server details."""
    server = PlexServer(base_url.rstrip("/"), token)
    return {
        CONF_BASE_URL: str(server._baseurl),
        CONF_SERVER_TOKEN: token,
        CONF_MACHINE_IDENTIFIER: str(server.machineIdentifier),
        CONF_SERVER_NAME: str(server.friendlyName),
    }


class PlexExtendedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle Plex Extended configuration."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self.plexauth: PlexAuth | None = None
        self._account_token: str | None = None
        self._client_id: str | None = None
        self._resources: dict[str, Any] = {}
        self._reauth_entry: ConfigEntry | None = None
        self._target_machine_identifier: str | None = None

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> PlexExtendedOptionsFlow:
        """Return the Plex Extended options flow."""
        return PlexExtendedOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start user configuration."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["website_auth", "manual_setup"],
        )

    async def async_step_website_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start Plex-hosted account authorization."""
        return await self._async_start_plex_auth()

    async def _async_start_plex_auth(self) -> ConfigFlowResult:
        """Create a Plex PIN authorization and send the browser to Plex."""
        self.hass.http.register_view(PlexExtendedAuthorizationCallbackView)

        request = http.current_request.get()
        if request is None:
            return self.async_abort(reason="missing_request")
        hass_url = request.headers.get(HEADER_FRONTEND_BASE)
        if not hass_url:
            return self.async_abort(reason="missing_frontend_url")

        payload = {
            "X-Plex-Device-Name": X_PLEX_DEVICE_NAME,
            "X-Plex-Version": X_PLEX_VERSION,
            "X-Plex-Product": X_PLEX_PRODUCT,
            "X-Plex-Device": self.hass.config.location_name,
            "X-Plex-Platform": X_PLEX_PLATFORM,
            "X-Plex-Model": "Plex OAuth",
        }
        session = async_get_clientsession(self.hass)
        self.plexauth = PlexAuth(payload, session, {"Origin": hass_url})
        await self.plexauth.initiate_auth()

        forward_url = f"{hass_url}{AUTH_CALLBACK_PATH}?flow_id={self.flow_id}"
        return self.async_external_step(
            step_id="obtain_token",
            url=self.plexauth.auth_url(forward_url),
        )

    async def async_step_obtain_token(
        self, user_input: None = None
    ) -> ConfigFlowResult:
        """Receive the Plex token after website authorization."""
        if self.plexauth is None:
            return self.async_abort(reason="auth_not_started")

        token = await self.plexauth.token(10)
        if not token:
            return self.async_external_step_done(next_step_id="timed_out")

        self._account_token = token
        self._client_id = self.plexauth.client_identifier
        return self.async_external_step_done(next_step_id="discover_servers")

    async def async_step_timed_out(
        self, user_input: None = None
    ) -> ConfigFlowResult:
        """Abort when Plex authorization times out."""
        return self.async_abort(reason="token_request_timeout")

    async def async_step_discover_servers(
        self, user_input: None = None
    ) -> ConfigFlowResult:
        """Discover servers linked to the newly authorized Plex account."""
        if not self._account_token:
            return self.async_abort(reason="auth_not_started")

        try:
            resources = await self.hass.async_add_executor_job(
                _discover_servers, self._account_token
            )
        except Unauthorized:
            return self.async_abort(reason="invalid_auth")
        except (RequestException, Exception):
            return self.async_abort(reason="cannot_connect")

        self._resources = {
            str(resource.clientIdentifier): resource for resource in resources
        }
        if not self._resources:
            return self.async_abort(reason="no_servers")

        if self._target_machine_identifier:
            if self._target_machine_identifier not in self._resources:
                return self.async_abort(reason="reauth_server_missing")
            return await self._async_finish_resource(self._target_machine_identifier)

        if len(self._resources) == 1:
            return await self._async_finish_resource(next(iter(self._resources)))

        return await self.async_step_select_server()

    async def async_step_select_server(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose a discovered Plex server."""
        if user_input is not None:
            return await self._async_finish_resource(user_input[CONF_MACHINE_IDENTIFIER])

        options = {
            identifier: (
                f"{resource.name} ({resource.sourceTitle})"
                if getattr(resource, "sourceTitle", None)
                else str(resource.name)
            )
            for identifier, resource in self._resources.items()
        }
        return self.async_show_form(
            step_id="select_server",
            data_schema=vol.Schema(
                {vol.Required(CONF_MACHINE_IDENTIFIER): vol.In(options)}
            ),
        )

    async def _async_finish_resource(self, identifier: str) -> ConfigFlowResult:
        """Validate the selected resource and create/update the entry."""
        resource = self._resources[identifier]
        try:
            data = await self.hass.async_add_executor_job(_connect_resource, resource)
        except Unauthorized:
            return self.async_abort(reason="invalid_auth")
        except Exception:
            return self.async_abort(reason="cannot_connect")

        if self._client_id:
            data[CONF_CLIENT_ID] = self._client_id
        return await self._async_create_or_update(data)

    async def async_step_manual_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow URL + token setup as a fallback."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = await self.hass.async_add_executor_job(
                    _connect_manual,
                    user_input[CONF_BASE_URL],
                    user_input[CONF_TOKEN],
                )
            except Unauthorized:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                return await self._async_create_or_update(data)

        return self.async_show_form(
            step_id="manual_setup",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BASE_URL): cv.url,
                    vol.Required(CONF_TOKEN): str,
                }
            ),
            errors=errors,
        )

    async def _async_create_or_update(
        self, data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Create a config entry or finish reauthentication."""
        machine_identifier = data[CONF_MACHINE_IDENTIFIER]
        await self.async_set_unique_id(machine_identifier)

        if self._reauth_entry is not None:
            return self.async_update_reload_and_abort(
                self._reauth_entry,
                data=data,
                reason="reauth_successful",
            )

        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=data[CONF_SERVER_NAME], data=data)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start a reauthentication flow."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="reauth_entry_missing")
        self._reauth_entry = entry
        self._target_machine_identifier = entry.data[CONF_MACHINE_IDENTIFIER]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to reconnect their Plex account."""
        if user_input is not None:
            return await self._async_start_plex_auth()
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({}),
        )


class PlexExtendedOptionsFlow(OptionsFlow):
    """Configure Plex Extended behavior that is not credential data."""

    @override
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the Plex user used for viewing-state queries by default."""
        client = self.config_entry.runtime_data
        if not isinstance(client, PlexExtendedClient):
            return self.async_abort(reason="not_loaded")

        try:
            users_result = await client.async_list_users()
        except PlexExtendedError:
            return self.async_abort(reason="cannot_load_users")

        choices: dict[str, str] = {
            "": "Configured Plex account / server owner",
        }
        for user in users_result.get("users", []):
            user_id = str(user.get("id", ""))
            name = str(user.get("name", ""))
            if user_id and name:
                choices[user_id] = f"{name} (ID {user_id})"

        errors: dict[str, str] = {}
        if user_input is not None:
            selected = str(user_input.get(CONF_DEFAULT_USER_ID, ""))
            if selected:
                try:
                    await async_validate_user_context(client, selected)
                except PlexExtendedError:
                    errors[CONF_DEFAULT_USER_ID] = "invalid_user_context"
                else:
                    options = dict(self.config_entry.options)
                    options[CONF_DEFAULT_USER_ID] = selected
                    return self.async_create_entry(title="", data=options)
            else:
                options = dict(self.config_entry.options)
                options.pop(CONF_DEFAULT_USER_ID, None)
                return self.async_create_entry(title="", data=options)

        current = str(self.config_entry.options.get(CONF_DEFAULT_USER_ID, ""))
        if current not in choices:
            current = ""
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEFAULT_USER_ID, default=current): vol.In(choices)}
            ),
            errors=errors,
        )


class PlexExtendedAuthorizationCallbackView(HomeAssistantView):
    """Receive the Plex website authorization callback."""

    url = AUTH_CALLBACK_PATH
    name = AUTH_CALLBACK_NAME
    requires_auth = False

    async def get(self, request: Any) -> web_response.Response:
        """Resume the matching Home Assistant config flow."""
        hass: HomeAssistant = request.app[KEY_HASS]
        flow_id = request.query.get("flow_id")
        if not flow_id:
            return web_response.Response(status=400, text="Missing flow_id")

        await hass.config_entries.flow.async_configure(flow_id=flow_id, user_input=None)
        return web_response.Response(
            text="""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Plex Extended connected</title>
  <style>
    :root { color-scheme: light dark; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: Canvas;
      color: CanvasText;
    }
    main { max-width: 34rem; padding: 2rem; text-align: center; }
    h1 { margin-bottom: .5rem; font-size: 1.6rem; }
    p { line-height: 1.5; opacity: .8; }
    a {
      display: inline-block;
      margin-top: .75rem;
      padding: .7rem 1rem;
      border-radius: .5rem;
      background: #03a9f4;
      color: white;
      text-decoration: none;
      font-weight: 600;
    }
  </style>
</head>
<body>
  <main>
    <h1>Plex Extended connected</h1>
    <p>Returning to Home Assistant…</p>
    <p>If this window does not close automatically, use the button below.</p>
    <a href="/">Return to Home Assistant</a>
  </main>
  <script>window.close();</script>
</body>
</html>
""",
            content_type="text/html",
            headers={"Cache-Control": "no-store"},
        )
