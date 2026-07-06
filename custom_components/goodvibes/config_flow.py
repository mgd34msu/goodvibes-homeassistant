"""Config flow for the GoodVibes integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from .client import (
    GoodVibesClient,
    GoodVibesClientError,
    GoodVibesSurfaceMissingError,
    GoodVibesUnauthorizedError,
    normalize_daemon_url,
)
from .const import (
    CONF_DAEMON_TOKEN,
    CONF_DAEMON_URL,
    CONF_EVENT_TYPE,
    CONF_HOME_GRAPH_ENABLED,
    CONF_INSTALLATION_ID,
    CONF_KNOWLEDGE_SPACE_ID,
    CONF_WEBHOOK_SECRET,
    DEFAULT_DAEMON_URL,
    DEFAULT_EVENT_TYPE,
    DEFAULT_DEVICE_NAME,
    DEFAULT_HOME_GRAPH_ENABLED,
    DOMAIN,
)
from .home_graph import build_home_graph_base_payload, derive_installation_id


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the user step schema."""

    defaults = defaults or {}
    password_selector = selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
    )
    return vol.Schema(
        {
            vol.Required(
                CONF_DAEMON_URL,
                default=defaults.get(CONF_DAEMON_URL, DEFAULT_DAEMON_URL),
            ): str,
            vol.Optional(
                CONF_DAEMON_TOKEN,
                default=defaults.get(CONF_DAEMON_TOKEN, ""),
            ): password_selector,
            vol.Required(
                CONF_WEBHOOK_SECRET,
                default=defaults.get(CONF_WEBHOOK_SECRET, ""),
            ): password_selector,
            vol.Optional(
                CONF_EVENT_TYPE,
                default=defaults.get(CONF_EVENT_TYPE, DEFAULT_EVENT_TYPE),
            ): str,
            vol.Optional(
                CONF_HOME_GRAPH_ENABLED,
                default=defaults.get(
                    CONF_HOME_GRAPH_ENABLED, DEFAULT_HOME_GRAPH_ENABLED
                ),
            ): bool,
            vol.Optional(
                CONF_INSTALLATION_ID,
                default=defaults.get(CONF_INSTALLATION_ID, ""),
            ): str,
            vol.Optional(
                CONF_KNOWLEDGE_SPACE_ID,
                default=defaults.get(CONF_KNOWLEDGE_SPACE_ID, ""),
            ): str,
        }
    )


class GoodVibesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GoodVibes."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                validated = await _validate_input(self.hass, user_input)
            except GoodVibesUnauthorizedError:
                errors["base"] = "invalid_auth"
            except GoodVibesSurfaceMissingError:
                errors["base"] = "surface_missing"
            except GoodVibesClientError:
                # Unreachable daemon, timeout, or any other daemon-side error.
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(validated["daemon_url"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=validated["title"],
                    data=validated["data"],
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input),
            errors=errors,
        )


async def _validate_input(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> dict[str, Any]:
    """Validate the daemon and Home Assistant surface endpoints."""

    daemon_url = normalize_daemon_url(user_input[CONF_DAEMON_URL])
    daemon_token = str(user_input.get(CONF_DAEMON_TOKEN) or "").strip()
    webhook_secret = str(user_input[CONF_WEBHOOK_SECRET]).strip()
    event_type = str(user_input.get(CONF_EVENT_TYPE) or DEFAULT_EVENT_TYPE).strip()
    home_graph_enabled = bool(
        user_input.get(CONF_HOME_GRAPH_ENABLED, DEFAULT_HOME_GRAPH_ENABLED)
    )
    installation_id = str(user_input.get(CONF_INSTALLATION_ID) or "").strip()
    if not installation_id:
        installation_id = derive_installation_id(hass)
    knowledge_space_id = str(user_input.get(CONF_KNOWLEDGE_SPACE_ID) or "").strip()

    if not webhook_secret:
        raise GoodVibesClientError("Home Assistant webhook secret is required")
    if not event_type:
        event_type = DEFAULT_EVENT_TYPE

    client = GoodVibesClient(hass, daemon_url, daemon_token, webhook_secret)
    await client.status()
    health = await client.health()
    if health.get("ok") is False:
        raise GoodVibesSurfaceMissingError("Home Assistant surface is disabled")
    if home_graph_enabled:
        await client.home_graph_status(
            build_home_graph_base_payload(
                installation_id,
                knowledge_space_id or None,
            )
        )
    raw_manifest = await client.manifest()
    manifest = raw_manifest.get("result", raw_manifest)

    device = manifest.get("device", {}) if isinstance(manifest, dict) else {}
    title = str(device.get("name") or DEFAULT_DEVICE_NAME)

    return {
        "daemon_url": daemon_url,
        "title": title,
        "data": {
            CONF_DAEMON_URL: daemon_url,
            CONF_DAEMON_TOKEN: daemon_token,
            CONF_WEBHOOK_SECRET: webhook_secret,
            CONF_EVENT_TYPE: event_type,
            CONF_HOME_GRAPH_ENABLED: home_graph_enabled,
            CONF_INSTALLATION_ID: installation_id,
            CONF_KNOWLEDGE_SPACE_ID: knowledge_space_id,
        },
    }
