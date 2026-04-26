"""Home Assistant integration for GoodVibes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .client import GoodVibesClient, GoodVibesClientError
from .const import (
    CONF_AGENT_ID,
    CONF_AREA_ID,
    CONF_CONFIG_ENTRY_ID,
    CONF_CONVERSATION_ID,
    CONF_DAEMON_TOKEN,
    CONF_DAEMON_URL,
    CONF_DEVICE_ID,
    CONF_DISPLAY_NAME,
    CONF_ENTITY_ID,
    CONF_EVENT_TYPE,
    CONF_INPUT,
    CONF_INPUT_ID,
    CONF_MESSAGE_ID,
    CONF_MODEL_ID,
    CONF_PROVIDER_ID,
    CONF_RUN_ID,
    CONF_SESSION_ID,
    CONF_TASK,
    CONF_TASK_ID,
    CONF_TOOL,
    CONF_TOOLS,
    CONF_USER_ID,
    CONF_WEBHOOK_SECRET,
    DEFAULT_CONVERSATION_ID,
    DEFAULT_DEVICE_ID,
    DEFAULT_DEVICE_NAME,
    DEFAULT_DISPLAY_NAME,
    DEFAULT_EVENT_TYPE,
    DOMAIN,
    PLATFORMS,
    SIGNAL_UPDATE,
    TERMINAL_STATUSES,
)

SERVICE_PROMPT = "prompt"
SERVICE_RUN_AGENT = "run_agent"
SERVICE_STATUS = "status"
SERVICE_CANCEL = "cancel"
SERVICE_CALL_TOOL = "call_tool"


def _optional_context_schema() -> dict[Any, Any]:
    """Return optional prompt context fields shared by prompt and run_agent."""

    return {
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(CONF_CONVERSATION_ID, default=DEFAULT_CONVERSATION_ID): cv.string,
        vol.Optional(CONF_DEVICE_ID, default=DEFAULT_DEVICE_ID): cv.string,
        vol.Optional(CONF_ENTITY_ID): cv.string,
        vol.Optional(CONF_AREA_ID): cv.string,
        vol.Optional(CONF_USER_ID): cv.string,
        vol.Optional(CONF_DISPLAY_NAME, default=DEFAULT_DISPLAY_NAME): cv.string,
        vol.Optional(CONF_MESSAGE_ID): cv.string,
        vol.Optional(CONF_PROVIDER_ID): cv.string,
        vol.Optional(CONF_MODEL_ID): cv.string,
        vol.Optional(CONF_TOOLS): vol.All(cv.ensure_list, [cv.string]),
    }


PROMPT_SCHEMA = vol.Schema(
    {
        vol.Required("message"): cv.string,
        **_optional_context_schema(),
    }
)

RUN_AGENT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TASK): cv.string,
        **_optional_context_schema(),
    }
)

STATUS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(CONF_AGENT_ID): cv.string,
        vol.Optional(CONF_RUN_ID): cv.string,
        vol.Optional(CONF_TASK_ID): cv.string,
        vol.Optional(CONF_SESSION_ID): cv.string,
    }
)

CANCEL_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(CONF_AGENT_ID): cv.string,
        vol.Optional(CONF_RUN_ID): cv.string,
        vol.Optional(CONF_TASK_ID): cv.string,
        vol.Optional(CONF_SESSION_ID): cv.string,
        vol.Optional(CONF_INPUT_ID): cv.string,
        vol.Optional(CONF_MESSAGE_ID): cv.string,
    }
)

CALL_TOOL_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
        vol.Required(CONF_TOOL): cv.string,
        vol.Optional(CONF_INPUT, default=dict): dict,
    }
)


def _result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Unwrap daemon channel action envelopes."""

    result = payload.get("result")
    return result if isinstance(result, dict) else payload


def _truncate_state(value: Any, limit: int = 255) -> str | None:
    """Return a Home Assistant state-safe string."""

    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


@dataclass
class GoodVibesRuntimeData:
    """Runtime state shared by GoodVibes entities and services."""

    hass: HomeAssistant
    entry: ConfigEntry
    client: GoodVibesClient
    event_type: str
    manifest: dict[str, Any] = field(default_factory=dict)
    health: dict[str, Any] = field(default_factory=dict)
    daemon_status: dict[str, Any] = field(default_factory=dict)
    homeassistant_status: dict[str, Any] = field(default_factory=dict)
    tool_catalog: dict[str, Any] = field(default_factory=dict)
    status: str = "unknown"
    last_reply: str | None = None
    last_payload: dict[str, Any] = field(default_factory=dict)
    last_error: str | None = None
    last_event_at: str | None = None
    active_session_id: str | None = None
    active_agent_id: str | None = None
    active_run_id: str | None = None
    unsubscribe_event: Any | None = None

    @property
    def signal(self) -> str:
        """Return this entry's dispatcher signal."""

        return f"{SIGNAL_UPDATE}_{self.entry.entry_id}"

    @property
    def device_identifier(self) -> str:
        """Return the registry identifier for the daemon device."""

        device = self.manifest.get("device", {})
        identifiers = device.get("identifiers")
        if isinstance(identifiers, list) and identifiers:
            return str(identifiers[0])
        return self.entry.unique_id or self.client.daemon_url

    @property
    def device_name(self) -> str:
        """Return the daemon device name."""

        device = self.manifest.get("device", {})
        return str(device.get("name") or DEFAULT_DEVICE_NAME)

    @property
    def device_model(self) -> str:
        """Return the daemon device model."""

        device = self.manifest.get("device", {})
        return str(device.get("model") or DEFAULT_DEVICE_NAME)

    @property
    def sw_version(self) -> str | None:
        """Return the daemon software version."""

        device = self.manifest.get("device", {})
        value = device.get("swVersion") or self.daemon_status.get("version")
        return str(value) if value else None

    async def async_initial_refresh(self) -> None:
        """Refresh daemon state without failing integration setup."""

        try:
            raw_manifest = await self.client.manifest()
            self.manifest = _result_payload(raw_manifest)
        except GoodVibesClientError as err:
            self.last_error = str(err)

        await self.async_refresh()

    async def async_refresh(self) -> None:
        """Refresh daemon status and tool catalog."""

        try:
            self.health = await self.client.health()
            self.daemon_status = await self.client.status()
            self.status = str(self.daemon_status.get("status") or "running")
            raw_surface_status = await self.client.homeassistant_status()
            self.homeassistant_status = _result_payload(raw_surface_status)
            if self.homeassistant_status.get("ok") is False:
                self.status = "homeassistant_error"
                self.last_error = str(
                    self.homeassistant_status.get("error") or "Home Assistant surface error"
                )
            self.tool_catalog = await self.client.tool_catalog()
            if self.status != "homeassistant_error":
                self.last_error = None
        except GoodVibesClientError as err:
            self.status = "error"
            self.last_error = str(err)
        finally:
            async_dispatcher_send(self.hass, self.signal)

    @callback
    def async_handle_event(self, event) -> None:
        """Handle an outbound GoodVibes Home Assistant bus event."""

        payload = dict(event.data)
        self.last_payload = payload
        self.last_event_at = dt_util.utcnow().isoformat()

        event_status = payload.get("status") or payload.get("type") or "message"
        self.status = _truncate_state(event_status) or "message"

        body = payload.get("body") or payload.get("message") or payload.get("text")
        title = payload.get("title")
        if body:
            self.last_reply = str(body)
        elif title:
            self.last_reply = str(title)

        session_id = payload.get("sessionId") or payload.get("session_id")
        agent_id = payload.get("agentId") or payload.get("agent_id")
        run_id = payload.get("runId") or payload.get("run_id") or payload.get("jobId")

        status_lower = str(event_status).lower()
        if status_lower in TERMINAL_STATUSES:
            if agent_id is None or str(agent_id) == self.active_agent_id:
                self.active_agent_id = None
            if session_id is None or str(session_id) == self.active_session_id:
                self.active_session_id = None
            if run_id is None or str(run_id) == self.active_run_id:
                self.active_run_id = None
        else:
            if session_id:
                self.active_session_id = str(session_id)
            if agent_id:
                self.active_agent_id = str(agent_id)
            if run_id:
                self.active_run_id = str(run_id)

        if status_lower in {"error", "failed"}:
            self.last_error = str(body or title or "GoodVibes reported an error")

        async_dispatcher_send(self.hass, self.signal)

    @callback
    def async_apply_submission_response(self, response: dict[str, Any]) -> None:
        """Update active ids from a daemon submission response."""

        if session_id := response.get("sessionId"):
            self.active_session_id = str(session_id)
        if agent_id := response.get("agentId"):
            self.active_agent_id = str(agent_id)
        self.status = "queued" if response.get("queued") else "acknowledged"
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def async_apply_conversation_response(self, response: dict[str, Any]) -> None:
        """Update runtime state from a synchronous conversation response."""

        if session_id := response.get("sessionId"):
            self.active_session_id = str(session_id)
        if agent_id := response.get("agentId"):
            self.active_agent_id = str(agent_id)
        assistant = response.get("assistant")
        if isinstance(assistant, dict):
            reply = assistant.get("speechText") or assistant.get("text")
            if reply:
                self.last_reply = str(reply)
        self.status = str(response.get("status") or response.get("mode") or "conversation")
        if response.get("ok") is False:
            self.last_error = str(response.get("error") or "GoodVibes conversation failed")
        else:
            self.last_error = None
        async_dispatcher_send(self.hass, self.signal)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up GoodVibes services."""

    hass.data.setdefault(DOMAIN, {})
    if hass.data[DOMAIN].get("services_registered"):
        return True

    async def async_prompt(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = _prompt_payload(call.data, message_key="message", body_type="prompt")
        response = await _call_client(runtime.client.prompt(payload))
        runtime.async_apply_submission_response(response)
        return response

    async def async_run_agent(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = _prompt_payload(call.data, message_key=CONF_TASK, body_type="agent")
        payload["task"] = payload.pop("message")
        response = await _call_client(runtime.client.run_agent(payload))
        runtime.async_apply_submission_response(response)
        return response

    async def async_status(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        if task_id := call.data.get(CONF_TASK_ID):
            return await _call_client(runtime.client.runtime_task(task_id))
        if agent_id := call.data.get(CONF_AGENT_ID):
            return await _call_client(runtime.client.agent_status(agent_id))
        if session_id := call.data.get(CONF_SESSION_ID):
            return await _call_client(runtime.client.session(session_id))
        if run_id := call.data.get(CONF_RUN_ID):
            return await _call_client(runtime.client.control_command("status", run_id))
        await runtime.async_refresh()
        return {
            "daemon": runtime.daemon_status,
            "homeassistant": runtime.homeassistant_status,
            "tools": runtime.tool_catalog,
        }

    async def async_cancel(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        if task_id := call.data.get(CONF_TASK_ID):
            response = await _call_client(runtime.client.cancel_task(task_id))
        elif call.data.get(CONF_SESSION_ID) and call.data.get(CONF_INPUT_ID):
            response = await _call_client(
                runtime.client.cancel_session_input(
                    call.data[CONF_SESSION_ID], call.data[CONF_INPUT_ID]
                )
            )
        else:
            agent_id = call.data.get(CONF_AGENT_ID) or runtime.active_agent_id
            message_id = call.data.get(CONF_MESSAGE_ID)
            if agent_id or message_id:
                response = await _call_client(
                    runtime.client.cancel_conversation(
                        agent_id=agent_id,
                        message_id=message_id,
                    )
                )
            elif run_id := call.data.get(CONF_RUN_ID) or runtime.active_run_id:
                response = await _call_client(runtime.client.control_command("cancel", run_id))
            else:
                raise HomeAssistantError(
                    "cancel requires agent_id, message_id, run_id, task_id, "
                    "session_id/input_id, or an active GoodVibes run"
                )
        runtime.status = "cancelled"
        runtime.active_agent_id = None
        runtime.active_run_id = None
        async_dispatcher_send(hass, runtime.signal)
        return response

    async def async_call_tool(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        return await _call_client(
            runtime.client.call_tool(call.data[CONF_TOOL], call.data.get(CONF_INPUT, {}))
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_PROMPT,
        async_prompt,
        schema=PROMPT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_AGENT,
        async_run_agent,
        schema=RUN_AGENT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STATUS,
        async_status,
        schema=STATUS_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL,
        async_cancel,
        schema=CANCEL_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CALL_TOOL,
        async_call_tool,
        schema=CALL_TOOL_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.data[DOMAIN]["services_registered"] = True
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GoodVibes from a config entry."""

    client = GoodVibesClient(
        hass,
        entry.data[CONF_DAEMON_URL],
        entry.data.get(CONF_DAEMON_TOKEN),
        entry.data[CONF_WEBHOOK_SECRET],
    )
    runtime = GoodVibesRuntimeData(
        hass=hass,
        entry=entry,
        client=client,
        event_type=entry.data.get(CONF_EVENT_TYPE, DEFAULT_EVENT_TYPE),
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = runtime

    await runtime.async_initial_refresh()
    runtime.unsubscribe_event = hass.bus.async_listen(
        runtime.event_type, runtime.async_handle_event
    )

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, runtime.device_identifier)},
        manufacturer="GoodVibes",
        model=runtime.device_model,
        name=runtime.device_name,
        sw_version=runtime.sw_version,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a GoodVibes config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime = hass.data[DOMAIN].pop(entry.entry_id, None)
        if runtime and runtime.unsubscribe_event:
            runtime.unsubscribe_event()
    return unload_ok


def _runtime_from_service_call(
    hass: HomeAssistant, call: ServiceCall
) -> GoodVibesRuntimeData:
    """Resolve the runtime targeted by a service call."""

    entries = {
        key: value
        for key, value in hass.data.get(DOMAIN, {}).items()
        if isinstance(value, GoodVibesRuntimeData)
    }
    entry_id = call.data.get(CONF_CONFIG_ENTRY_ID)
    if entry_id:
        runtime = entries.get(entry_id)
        if runtime is None:
            raise HomeAssistantError(f"Unknown GoodVibes config_entry_id: {entry_id}")
        return runtime
    if len(entries) == 1:
        return next(iter(entries.values()))
    if not entries:
        raise HomeAssistantError("No GoodVibes config entry is loaded")
    raise HomeAssistantError("config_entry_id is required when multiple entries exist")


def _prompt_payload(
    data: dict[str, Any], *, message_key: str, body_type: str
) -> dict[str, Any]:
    """Build the canonical daemon webhook prompt payload."""

    payload: dict[str, Any] = {
        "type": body_type,
        "message": data[message_key],
        "conversationId": data.get(CONF_CONVERSATION_ID, DEFAULT_CONVERSATION_ID),
        "deviceId": data.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID),
        "displayName": data.get(CONF_DISPLAY_NAME, DEFAULT_DISPLAY_NAME),
    }
    optional_fields = {
        "entityId": CONF_ENTITY_ID,
        "areaId": CONF_AREA_ID,
        "userId": CONF_USER_ID,
        "messageId": CONF_MESSAGE_ID,
        "providerId": CONF_PROVIDER_ID,
        "modelId": CONF_MODEL_ID,
    }
    for payload_key, config_key in optional_fields.items():
        if value := data.get(config_key):
            payload[payload_key] = value
    if tools := data.get(CONF_TOOLS):
        payload["tools"] = list(tools)
    return payload


async def _call_client(awaitable) -> dict[str, Any]:
    """Call the daemon client and convert errors for Home Assistant."""

    try:
        return await awaitable
    except GoodVibesClientError as err:
        raise HomeAssistantError(str(err)) from err
