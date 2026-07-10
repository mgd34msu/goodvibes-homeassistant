"""Config flow for the GoodVibes integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_LLM_HASS_API
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import llm, selector

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
    CONF_HABIT_MINING_ENABLED,
    CONF_HABIT_RETENTION_DAYS,
    CONF_HOME_GRAPH_ENABLED,
    CONF_INCLUDE_UNEXPOSED_ENTITIES,
    CONF_INSTALLATION_ID,
    CONF_KNOWLEDGE_SPACE_ID,
    CONF_PERCEPTION_ENABLED,
    CONF_PERCEPTION_ENTITIES,
    CONF_PERCEPTION_PROMPT,
    CONF_PROMPT,
    CONF_WEBHOOK_SECRET,
    DEFAULT_DAEMON_URL,
    DEFAULT_EVENT_TYPE,
    DEFAULT_DEVICE_NAME,
    DEFAULT_HABIT_MINING_ENABLED,
    DEFAULT_HABIT_RETENTION_DAYS,
    DEFAULT_HOME_GRAPH_ENABLED,
    DEFAULT_INCLUDE_UNEXPOSED_ENTITIES,
    DEFAULT_PERCEPTION_ENABLED,
    HABIT_RETENTION_DAYS_MAX,
    HABIT_RETENTION_DAYS_MIN,
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
                CONF_INCLUDE_UNEXPOSED_ENTITIES,
                default=defaults.get(
                    CONF_INCLUDE_UNEXPOSED_ENTITIES,
                    DEFAULT_INCLUDE_UNEXPOSED_ENTITIES,
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

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow for the conversation agent settings."""

        return GoodVibesOptionsFlow()

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


class GoodVibesOptionsFlow(config_entries.OptionsFlow):
    """Conversation-agent options: the Assist LLM API and a custom prompt.

    These mirror the settings a first-class Home Assistant conversation agent
    exposes. They are read by the conversation entity, which routes them through
    ``homeassistant.helpers.llm`` to assemble the system prompt (see
    ``conversation.py``).
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the conversation options."""

        if user_input is not None:
            # An empty selection means "no HA LLM API"; drop the key so the
            # conversation entity treats it as unset rather than an empty list.
            options = {CONF_PROMPT: user_input.get(CONF_PROMPT, "").strip()}
            if not options[CONF_PROMPT]:
                options.pop(CONF_PROMPT)
            if llm_apis := user_input.get(CONF_LLM_HASS_API):
                options[CONF_LLM_HASS_API] = llm_apis
            # Perception triggers: off unless explicitly enabled with entities.
            options[CONF_PERCEPTION_ENABLED] = bool(
                user_input.get(CONF_PERCEPTION_ENABLED, DEFAULT_PERCEPTION_ENABLED)
            )
            if entities := user_input.get(CONF_PERCEPTION_ENTITIES):
                options[CONF_PERCEPTION_ENTITIES] = list(entities)
            if perception_prompt := (
                user_input.get(CONF_PERCEPTION_PROMPT) or ""
            ).strip():
                options[CONF_PERCEPTION_PROMPT] = perception_prompt
            # Habit mining: off unless explicitly enabled. Retention days are
            # clamped to the honest in-memory window bounds.
            options[CONF_HABIT_MINING_ENABLED] = bool(
                user_input.get(CONF_HABIT_MINING_ENABLED, DEFAULT_HABIT_MINING_ENABLED)
            )
            retention_days = user_input.get(
                CONF_HABIT_RETENTION_DAYS, DEFAULT_HABIT_RETENTION_DAYS
            )
            try:
                retention_days = int(retention_days)
            except (TypeError, ValueError):
                retention_days = DEFAULT_HABIT_RETENTION_DAYS
            options[CONF_HABIT_RETENTION_DAYS] = max(
                HABIT_RETENTION_DAYS_MIN,
                min(HABIT_RETENTION_DAYS_MAX, retention_days),
            )
            return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(self.hass, self.config_entry.options),
        )


def _options_schema(
    hass: HomeAssistant, options: dict[str, Any]
) -> vol.Schema:
    """Return the conversation options schema seeded with current values."""

    hass_apis = [
        selector.SelectOptionDict(label=api.name, value=api.id)
        for api in llm.async_get_apis(hass)
    ]
    prompt_default = options.get(CONF_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT)
    schema: dict[Any, Any] = {
        vol.Optional(
            CONF_PROMPT,
            description={"suggested_value": prompt_default},
        ): selector.TemplateSelector(),
    }
    if hass_apis:
        schema[
            vol.Optional(
                CONF_LLM_HASS_API,
                default=options.get(CONF_LLM_HASS_API, []),
            )
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=hass_apis, multiple=True)
        )
    schema[
        vol.Optional(
            CONF_PERCEPTION_ENABLED,
            default=options.get(CONF_PERCEPTION_ENABLED, DEFAULT_PERCEPTION_ENABLED),
        )
    ] = selector.BooleanSelector()
    schema[
        vol.Optional(
            CONF_PERCEPTION_ENTITIES,
            default=options.get(CONF_PERCEPTION_ENTITIES, []),
        )
    ] = selector.EntitySelector(selector.EntitySelectorConfig(multiple=True))
    schema[
        vol.Optional(
            CONF_PERCEPTION_PROMPT,
            description={
                "suggested_value": options.get(CONF_PERCEPTION_PROMPT, "")
            },
        )
    ] = selector.TextSelector(
        selector.TextSelectorConfig(multiline=True)
    )
    schema[
        vol.Optional(
            CONF_HABIT_MINING_ENABLED,
            default=options.get(
                CONF_HABIT_MINING_ENABLED, DEFAULT_HABIT_MINING_ENABLED
            ),
        )
    ] = selector.BooleanSelector()
    schema[
        vol.Optional(
            CONF_HABIT_RETENTION_DAYS,
            default=options.get(
                CONF_HABIT_RETENTION_DAYS, DEFAULT_HABIT_RETENTION_DAYS
            ),
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=HABIT_RETENTION_DAYS_MIN,
            max=HABIT_RETENTION_DAYS_MAX,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
        )
    )
    return vol.Schema(schema)


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
    include_unexposed_entities = bool(
        user_input.get(
            CONF_INCLUDE_UNEXPOSED_ENTITIES, DEFAULT_INCLUDE_UNEXPOSED_ENTITIES
        )
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
            CONF_INCLUDE_UNEXPOSED_ENTITIES: include_unexposed_entities,
            CONF_INSTALLATION_ID: installation_id,
            CONF_KNOWLEDGE_SPACE_ID: knowledge_space_id,
        },
    }
