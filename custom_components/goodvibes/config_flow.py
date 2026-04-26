"""Config flow for the GoodVibes integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from .client import GoodVibesClient, GoodVibesClientError, normalize_daemon_url
from .const import (
    CONF_DAEMON_TOKEN,
    CONF_DAEMON_URL,
    CONF_EVENT_TYPE,
    CONF_WEBHOOK_SECRET,
    DEFAULT_DAEMON_URL,
    DEFAULT_EVENT_TYPE,
    DEFAULT_DEVICE_NAME,
    DOMAIN,
)


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the user step schema."""

    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_DAEMON_URL,
                default=defaults.get(CONF_DAEMON_URL, DEFAULT_DAEMON_URL),
            ): str,
            vol.Optional(
                CONF_DAEMON_TOKEN,
                default=defaults.get(CONF_DAEMON_TOKEN, ""),
            ): str,
            vol.Required(
                CONF_WEBHOOK_SECRET,
                default=defaults.get(CONF_WEBHOOK_SECRET, ""),
            ): str,
            vol.Optional(
                CONF_EVENT_TYPE,
                default=defaults.get(CONF_EVENT_TYPE, DEFAULT_EVENT_TYPE),
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
            except GoodVibesClientError as err:
                message = str(err).lower()
                if "401" in message or "403" in message or "unauthorized" in message:
                    errors["base"] = "invalid_auth"
                elif "unknown channel action" in message or "404" in message:
                    errors["base"] = "surface_missing"
                else:
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

    if not webhook_secret:
        raise GoodVibesClientError("Home Assistant webhook secret is required")
    if not event_type:
        event_type = DEFAULT_EVENT_TYPE

    client = GoodVibesClient(hass, daemon_url, daemon_token, webhook_secret)
    await client.status()
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
        },
    }
