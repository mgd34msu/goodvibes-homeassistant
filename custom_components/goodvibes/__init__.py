"""Home Assistant integration for GoodVibes."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from .client import GoodVibesClient, GoodVibesClientError
from .const import (
    CONF_AGENT_ID,
    CONF_ALLOW_PRIVATE_HOSTS,
    CONF_AREA_ID,
    CONF_ARTIFACT_ID,
    CONF_CODE,
    CONF_CONFIRM,
    CONF_CONFIG_ENTRY_ID,
    CONF_CONVERSATION_ID,
    CONF_DAEMON_TOKEN,
    CONF_DAEMON_URL,
    CONF_DECISION,
    CONF_DEVICE_ID,
    CONF_DISPLAY_NAME,
    CONF_DRY_RUN,
    CONF_ENTITY_ID,
    CONF_EVENT_TYPE,
    CONF_FACT_ID,
    CONF_HOME_GRAPH_ENABLED,
    CONF_INCLUDE_CONFIDENCE,
    CONF_INCLUDE_LINKED_OBJECTS,
    CONF_INCLUDE_SOURCES,
    CONF_INPUT,
    CONF_INSTALLATION_ID,
    CONF_KNOWLEDGE_SPACE_ID,
    CONF_LIMIT,
    CONF_MESSAGE_ID,
    CONF_MODE,
    CONF_MODEL_ID,
    CONF_NODE_ID,
    CONF_NOTE,
    CONF_PACKET_TYPE,
    CONF_PATH,
    CONF_PROVIDER_ID,
    CONF_QUERY,
    CONF_RELATION,
    CONF_RUN_ID,
    CONF_SESSION_ID,
    CONF_SEVERITY,
    CONF_SOURCE_ID,
    CONF_STATUS,
    CONF_TASK,
    CONF_TASK_ID,
    CONF_TARGET_ID,
    CONF_TARGET_KIND,
    CONF_TITLE,
    CONF_TOOL,
    CONF_TOOLS,
    CONF_TAGS,
    CONF_URI,
    CONF_URL,
    CONF_USER_ID,
    CONF_VALUE,
    CONF_WEBHOOK_SECRET,
    DEFAULT_CONVERSATION_ID,
    DEFAULT_DEVICE_ID,
    DEFAULT_DEVICE_NAME,
    DEFAULT_DISPLAY_NAME,
    DEFAULT_EVENT_TYPE,
    DEFAULT_HOME_GRAPH_ENABLED,
    DOMAIN,
    PLATFORMS,
    SIGNAL_UPDATE,
    TERMINAL_STATUSES,
)
from .home_graph import (
    async_build_home_graph_snapshot,
    build_home_graph_base_payload,
    default_knowledge_space_id,
    derive_installation_id,
)
from .daemon_payloads import (
    MAP_GENERIC_FIELDS,
    MAP_HA_FIELDS,
    copy_optional as _copy_optional,
    copy_optional_list as _copy_optional_list,
    copy_tags_and_private_hosts as _copy_tags_and_private_hosts,
    ensure_home_graph_enabled as _ensure_home_graph_enabled,
    home_graph_payload as _home_graph_payload,
    link_payload as _knowledge_link_payload,
    map_payload as _map_payload,
    prompt_payload as _prompt_payload,
)
from .frontend import async_setup_frontend, async_unload_frontend_panel

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_PROMPT = "prompt"
SERVICE_RUN_AGENT = "run_agent"
SERVICE_STATUS = "status"
SERVICE_CANCEL = "cancel"
SERVICE_CALL_TOOL = "call_tool"
SERVICE_HOME_GRAPH_STATUS = "home_graph_status"
SERVICE_SYNC_HOME_GRAPH = "sync_home_graph"
SERVICE_INGEST_URL = "ingest_url"
SERVICE_INGEST_NOTE = "ingest_note"
SERVICE_INGEST_ARTIFACT = "ingest_artifact"
SERVICE_LINK_KNOWLEDGE = "link_knowledge"
SERVICE_UNLINK_KNOWLEDGE = "unlink_knowledge"
SERVICE_ASK_HOME_GRAPH = "ask_home_graph"
SERVICE_DEVICE_PASSPORT = "device_passport"
SERVICE_ROOM_PAGE = "room_page"
SERVICE_HOME_GRAPH_PACKET = "home_graph_packet"
SERVICE_HOME_GRAPH_ISSUES = "home_graph_issues"
SERVICE_REVIEW_FACT = "review_fact"
SERVICE_HOME_GRAPH_SOURCES = "home_graph_sources"
SERVICE_HOME_GRAPH_PAGES = "home_graph_pages"
SERVICE_HOME_GRAPH_BROWSE = "home_graph_browse"
SERVICE_HOME_GRAPH_MAP = "home_graph_map"
SERVICE_HOME_GRAPH_EXPORT = "home_graph_export"
SERVICE_HOME_GRAPH_IMPORT = "home_graph_import"
SERVICE_HOME_GRAPH_RESET = "home_graph_reset"
SERVICE_HOME_GRAPH_REINDEX = "home_graph_reindex"


def _map_list_field(value: Any) -> str | list[str]:
    """Validate a comma string or native list service field."""

    if isinstance(value, str):
        return value
    return vol.All(cv.ensure_list, [cv.string])(value)


MAP_LIST_FIELD = _map_list_field
# The map filter field lists (snake_case service key -> camelCase daemon key)
# are owned by daemon_payloads so the service schema and the panel share one
# source of truth. The schema iterates these keys; the payload builder maps them.
MAP_GENERIC_SERVICE_FIELDS = MAP_GENERIC_FIELDS
MAP_HA_SERVICE_FIELDS = MAP_HA_FIELDS


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
        vol.Optional(CONF_RUN_ID): cv.string,
        vol.Optional(CONF_TASK_ID): cv.string,
        vol.Optional(CONF_SESSION_ID): cv.string,
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


def _home_graph_common_schema() -> dict[Any, Any]:
    """Return common Home Graph service fields."""

    return {
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(CONF_INSTALLATION_ID): cv.string,
        vol.Optional(CONF_KNOWLEDGE_SPACE_ID): cv.string,
    }


def _home_graph_target_schema() -> dict[Any, Any]:
    """Return optional Home Graph target fields."""

    return {
        vol.Optional(CONF_TARGET_KIND): cv.string,
        vol.Optional(CONF_TARGET_ID): cv.string,
        vol.Optional(CONF_RELATION): cv.string,
    }


HOME_GRAPH_COMMON_SCHEMA = vol.Schema(_home_graph_common_schema())

SYNC_HOME_GRAPH_SCHEMA = vol.Schema(_home_graph_common_schema())

INGEST_URL_SCHEMA = vol.Schema(
    {
        **_home_graph_common_schema(),
        vol.Required(CONF_URL): cv.string,
        vol.Optional(CONF_TITLE): cv.string,
        vol.Optional(CONF_TAGS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_ALLOW_PRIVATE_HOSTS): bool,
        vol.Optional("metadata", default=dict): dict,
        **_home_graph_target_schema(),
    }
)

INGEST_NOTE_SCHEMA = vol.Schema(
    {
        **_home_graph_common_schema(),
        vol.Required(CONF_NOTE): cv.string,
        vol.Optional(CONF_TITLE): cv.string,
        vol.Optional("category"): cv.string,
        vol.Optional(CONF_TAGS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("metadata", default=dict): dict,
        **_home_graph_target_schema(),
    }
)

INGEST_ARTIFACT_SCHEMA = vol.Schema(
    {
        **_home_graph_common_schema(),
        vol.Optional(CONF_ARTIFACT_ID): cv.string,
        vol.Optional(CONF_PATH): cv.string,
        vol.Optional(CONF_URI): cv.string,
        vol.Optional(CONF_URL): cv.string,
        vol.Optional(CONF_TITLE): cv.string,
        vol.Optional(CONF_TAGS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_ALLOW_PRIVATE_HOSTS): bool,
        vol.Optional("metadata", default=dict): dict,
        **_home_graph_target_schema(),
    }
)

LINK_KNOWLEDGE_SCHEMA = vol.Schema(
    {
        **_home_graph_common_schema(),
        vol.Optional(CONF_SOURCE_ID): cv.string,
        vol.Optional(CONF_NODE_ID): cv.string,
        vol.Required(CONF_TARGET_KIND): cv.string,
        vol.Required(CONF_TARGET_ID): cv.string,
        vol.Optional(CONF_RELATION): cv.string,
    }
)

UNLINK_KNOWLEDGE_SCHEMA = LINK_KNOWLEDGE_SCHEMA

ASK_HOME_GRAPH_SCHEMA = vol.Schema(
    {
        **_home_graph_common_schema(),
        vol.Required(CONF_QUERY): cv.string,
        vol.Optional(CONF_LIMIT): vol.Coerce(int),
        vol.Optional(CONF_MODE): cv.string,
        vol.Optional(CONF_INCLUDE_SOURCES, default=True): bool,
        vol.Optional(CONF_INCLUDE_CONFIDENCE, default=False): bool,
        vol.Optional(CONF_INCLUDE_LINKED_OBJECTS, default=True): bool,
    }
)

DEVICE_PASSPORT_SCHEMA = vol.Schema(
    {
        **_home_graph_common_schema(),
        vol.Optional(CONF_DEVICE_ID): cv.string,
    }
)

ROOM_PAGE_SCHEMA = vol.Schema(
    {
        **_home_graph_common_schema(),
        vol.Optional(CONF_AREA_ID): cv.string,
    }
)

HOME_GRAPH_PACKET_SCHEMA = vol.Schema(
    {
        **_home_graph_common_schema(),
        vol.Required(CONF_PACKET_TYPE): cv.string,
        vol.Optional(CONF_AREA_ID): cv.string,
        vol.Optional(CONF_DEVICE_ID): cv.string,
        vol.Optional(CONF_ENTITY_ID): cv.string,
        vol.Optional("metadata", default=dict): dict,
    }
)

REVIEW_FACT_SCHEMA = vol.Schema(
    {
        **_home_graph_common_schema(),
        vol.Optional("issue_id"): cv.string,
        vol.Optional(CONF_FACT_ID): cv.string,
        vol.Optional(CONF_NODE_ID): cv.string,
        vol.Optional(CONF_SOURCE_ID): cv.string,
        vol.Optional("action"): cv.string,
        vol.Optional(CONF_DECISION): cv.string,
        vol.Optional(CONF_VALUE): object,
        vol.Optional("reviewer"): cv.string,
    }
)

HOME_GRAPH_ISSUES_SCHEMA = vol.Schema(
    {
        **_home_graph_common_schema(),
        vol.Optional(CONF_STATUS): cv.string,
        vol.Optional(CONF_SEVERITY): cv.string,
        vol.Optional(CONF_CODE): cv.string,
        vol.Optional(CONF_LIMIT): vol.Coerce(int),
    }
)

HOME_GRAPH_LIST_SCHEMA = vol.Schema(
    {
        **_home_graph_common_schema(),
        vol.Optional(CONF_LIMIT): vol.Coerce(int),
    }
)

HOME_GRAPH_PAGES_SCHEMA = vol.Schema(
    {
        **_home_graph_common_schema(),
        vol.Optional(CONF_LIMIT): vol.Coerce(int),
        vol.Optional("include_markdown", default=True): bool,
    }
)

HOME_GRAPH_MAP_SCHEMA = vol.Schema(
    {
        **_home_graph_common_schema(),
        vol.Optional(CONF_LIMIT): vol.Coerce(int),
        vol.Optional(CONF_QUERY): cv.string,
        vol.Optional(CONF_INCLUDE_SOURCES, default=True): bool,
        vol.Optional("include_issues", default=False): bool,
        vol.Optional("include_generated", default=True): bool,
        vol.Optional("min_confidence"): vol.Coerce(float),
        **{
            vol.Optional(field): MAP_LIST_FIELD
            for field in MAP_GENERIC_SERVICE_FIELDS
        },
        **{
            vol.Optional(field): MAP_LIST_FIELD
            for field in MAP_HA_SERVICE_FIELDS
        },
    }
)

HOME_GRAPH_IMPORT_SCHEMA = vol.Schema(
    {
        **_home_graph_common_schema(),
        vol.Required("data"): dict,
    }
)

HOME_GRAPH_RESET_SCHEMA = vol.Schema(
    {
        **_home_graph_common_schema(),
        vol.Optional(CONF_CONFIRM): cv.string,
        vol.Optional(CONF_DRY_RUN, default=False): bool,
    }
)

HOME_GRAPH_REINDEX_SCHEMA = vol.Schema(_home_graph_common_schema())


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
    home_graph_enabled: bool
    installation_id: str
    knowledge_space_id: str | None
    manifest: dict[str, Any] = field(default_factory=dict)
    health: dict[str, Any] = field(default_factory=dict)
    daemon_status: dict[str, Any] = field(default_factory=dict)
    homeassistant_status: dict[str, Any] = field(default_factory=dict)
    tool_catalog: dict[str, Any] = field(default_factory=dict)
    home_graph_status: dict[str, Any] = field(default_factory=dict)
    home_graph_issues: dict[str, Any] = field(default_factory=dict)
    home_graph_sources: dict[str, Any] = field(default_factory=dict)
    home_graph_pages: dict[str, Any] = field(default_factory=dict)
    home_graph_refinement_tasks: dict[str, Any] = field(default_factory=dict)
    status: str = "unknown"
    last_reply: str | None = None
    last_payload: dict[str, Any] = field(default_factory=dict)
    last_error: str | None = None
    last_event_at: str | None = None
    home_graph_last_sync_at: str | None = None
    home_graph_last_response: dict[str, Any] = field(default_factory=dict)
    home_graph_last_error: str | None = None
    active_session_id: str | None = None
    active_message_id: str | None = None
    active_agent_id: str | None = None
    active_run_id: str | None = None
    unsubscribe_event: Any | None = None
    unsubscribe_auto_sync: Any | None = None

    @property
    def signal(self) -> str:
        """Return this entry's dispatcher signal."""

        return f"{SIGNAL_UPDATE}_{self.entry.entry_id}"

    @property
    def effective_knowledge_space_id(self) -> str:
        """Return the Home Graph knowledge space id."""

        return self.knowledge_space_id or default_knowledge_space_id(
            self.installation_id
        )

    def home_graph_base_payload(
        self, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return common Home Graph payload fields for this config entry."""

        data = data or {}
        installation_id = str(data.get(CONF_INSTALLATION_ID) or self.installation_id)
        knowledge_space_id = str(
            data.get(CONF_KNOWLEDGE_SPACE_ID) or self.effective_knowledge_space_id
        )
        return build_home_graph_base_payload(installation_id, knowledge_space_id)

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
            await self.async_refresh_home_graph()
            async_dispatcher_send(self.hass, self.signal)

    async def async_refresh_home_graph(self) -> None:
        """Refresh daemon Home Graph status without failing core status."""

        if not self.home_graph_enabled:
            self.home_graph_status = {"enabled": False, "status": "disabled"}
            self.home_graph_issues = {}
            self.home_graph_last_error = None
            _async_clear_home_graph_issue(self.hass, "home_graph_unavailable")
            _async_clear_home_graph_issue(self.hass, "home_graph_issues")
            return
        try:
            base_payload = self.home_graph_base_payload()
            self.home_graph_status = await self.client.home_graph_status(base_payload)
            self.home_graph_issues = await self.client.home_graph_issues(
                {**base_payload, CONF_STATUS: "open"}
            )
            self.home_graph_last_error = None
            _async_clear_home_graph_issue(self.hass, "home_graph_unavailable")
            issue_count = _home_graph_issue_count(self.home_graph_issues)
            if issue_count > 0:
                _async_create_home_graph_issue(
                    self.hass,
                    "home_graph_issues",
                    "home_graph_issues",
                    {"count": str(issue_count)},
                )
            else:
                _async_clear_home_graph_issue(self.hass, "home_graph_issues")
        except GoodVibesClientError as err:
            self.home_graph_status = {"ok": False, "status": "error"}
            self.home_graph_last_error = str(err)
            _async_clear_home_graph_issue(self.hass, "home_graph_issues")
            _async_create_home_graph_issue(
                self.hass,
                "home_graph_unavailable",
                "home_graph_unavailable",
                {"error": str(err)[:200]},
            )

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
        message_id = payload.get("messageId") or payload.get("message_id")
        agent_id = payload.get("agentId") or payload.get("agent_id")
        run_id = payload.get("runId") or payload.get("run_id") or payload.get("jobId")

        status_lower = str(event_status).lower()
        if status_lower in TERMINAL_STATUSES:
            if message_id is None or str(message_id) == self.active_message_id:
                self.active_message_id = None
            if agent_id is None or str(agent_id) == self.active_agent_id:
                self.active_agent_id = None
            if session_id is None or str(session_id) == self.active_session_id:
                self.active_session_id = None
            if run_id is None or str(run_id) == self.active_run_id:
                self.active_run_id = None
        else:
            if session_id:
                self.active_session_id = str(session_id)
            if message_id:
                self.active_message_id = str(message_id)
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
        if message_id := response.get("messageId"):
            self.active_message_id = str(message_id)
        if agent_id := response.get("agentId"):
            self.active_agent_id = str(agent_id)
        self.status = "queued" if response.get("queued") else "acknowledged"
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def async_start_conversation_turn(self, message_id: str) -> None:
        """Mark a synchronous remote-chat conversation turn as in progress."""

        self.active_message_id = message_id
        self.status = "processing"
        self.last_error = None
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def async_apply_conversation_response(self, response: dict[str, Any]) -> None:
        """Update runtime state from a synchronous conversation response."""

        response_status = (
            response.get("status") or response.get("mode") or "conversation"
        )
        if session_id := response.get("sessionId"):
            self.active_session_id = str(session_id)
        if message_id := response.get("messageId"):
            if str(message_id) == self.active_message_id:
                self.active_message_id = None
        elif str(response_status).lower() in TERMINAL_STATUSES:
            self.active_message_id = None
        if agent_id := response.get("agentId"):
            self.active_agent_id = str(agent_id)
        assistant = response.get("assistant")
        if isinstance(assistant, dict):
            reply = assistant.get("speechText") or assistant.get("text")
            if reply:
                self.last_reply = str(reply)
        self.status = str(response_status)
        if response.get("ok") is False:
            self.last_error = str(
                response.get("error") or "GoodVibes conversation failed"
            )
        else:
            self.last_error = None
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def async_apply_conversation_error(self, message_id: str, error: str) -> None:
        """Update runtime state when a synchronous conversation request fails."""

        if self.active_message_id == message_id:
            self.active_message_id = None
        self.status = "error"
        self.last_error = error
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def async_apply_home_graph_response(
        self,
        response: dict[str, Any],
        *,
        sync: bool = False,
    ) -> None:
        """Update runtime state from a Home Graph response."""

        self.home_graph_last_response = response
        if sync:
            self.home_graph_last_sync_at = dt_util.utcnow().isoformat()
        if response.get("ok") is False:
            self.home_graph_last_error = str(
                response.get("error") or "Home Graph request failed"
            )
        else:
            self.home_graph_last_error = None
        if status := response.get("status"):
            self.home_graph_status = {
                **self.home_graph_status,
                "status": status,
            }
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
            await runtime.async_refresh()
            return {
                "sessionId": session_id,
                "active": session_id == runtime.active_session_id,
                "activeMessageId": runtime.active_message_id,
                "status": runtime.status,
                "homeassistant": runtime.homeassistant_status,
                "health": runtime.health,
            }
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
        elif call.data.get(CONF_SESSION_ID) or call.data.get(CONF_MESSAGE_ID):
            response = await _call_client(
                runtime.client.cancel_conversation(
                    session_id=call.data.get(CONF_SESSION_ID),
                    message_id=call.data.get(CONF_MESSAGE_ID),
                )
            )
        elif run_id := call.data.get(CONF_RUN_ID):
            response = await _call_client(
                runtime.client.control_command("cancel", run_id)
            )
        else:
            session_id = runtime.active_session_id
            message_id = runtime.active_message_id
            if session_id or message_id:
                response = await _call_client(
                    runtime.client.cancel_conversation(
                        session_id=session_id,
                        message_id=message_id,
                    )
                )
            elif run_id := runtime.active_run_id:
                response = await _call_client(
                    runtime.client.control_command("cancel", run_id)
                )
            else:
                raise HomeAssistantError(
                    "cancel requires session_id, message_id, run_id, task_id, "
                    "or an active GoodVibes conversation"
                )
        runtime.status = "cancelled"
        runtime.active_message_id = None
        runtime.active_session_id = None
        runtime.active_agent_id = None
        runtime.active_run_id = None
        async_dispatcher_send(hass, runtime.signal)
        return response

    async def async_call_tool(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        return await _call_client(
            runtime.client.call_tool(call.data[CONF_TOOL], call.data.get(CONF_INPUT, {}))
        )

    async def async_home_graph_status(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        _ensure_home_graph_enabled(runtime)
        await runtime.async_refresh_home_graph()
        return {
            "status": runtime.home_graph_status,
            "issues": runtime.home_graph_issues,
            "sources": runtime.home_graph_sources,
            "pages": runtime.home_graph_pages,
            "lastSyncAt": runtime.home_graph_last_sync_at,
            "lastError": runtime.home_graph_last_error,
        }

    async def async_sync_home_graph(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        _ensure_home_graph_enabled(runtime)
        base_payload = runtime.home_graph_base_payload(call.data)
        snapshot = await async_build_home_graph_snapshot(
            hass,
            runtime.entry,
            base_payload["installationId"],
            base_payload.get("knowledgeSpaceId"),
        )
        response = await _call_client(runtime.client.home_graph_sync(snapshot))
        runtime.async_apply_home_graph_response(response, sync=True)
        _log_home_graph_sync(snapshot, response, trigger="service")
        await runtime.async_refresh_home_graph()
        return response

    async def async_sync_home_graph_context(
        runtime: GoodVibesRuntimeData,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _ensure_home_graph_enabled(runtime)
        base_payload = runtime.home_graph_base_payload(data or {})
        snapshot = await async_build_home_graph_snapshot(
            hass,
            runtime.entry,
            base_payload["installationId"],
            base_payload.get("knowledgeSpaceId"),
        )
        response = await _call_client(runtime.client.home_graph_sync(snapshot))
        runtime.async_apply_home_graph_response(response, sync=True)
        return response

    async def async_regenerate_home_graph_pages(
        runtime: GoodVibesRuntimeData,
        data: dict[str, Any] | None = None,
    ) -> None:
        try:
            await async_sync_home_graph_context(runtime, data)
        except HomeAssistantError as err:
            runtime.home_graph_last_error = str(err)
            async_dispatcher_send(hass, runtime.signal)

    async def async_ingest_url(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        await async_sync_home_graph_context(runtime, call.data)
        payload = {
            **_home_graph_payload(runtime, call.data),
            "url": call.data[CONF_URL],
        }
        _copy_optional(call.data, payload, CONF_TITLE, "title")
        _copy_tags_and_private_hosts(call.data, payload)
        response = await _call_client(runtime.client.home_graph_ingest_url(payload))
        runtime.async_apply_home_graph_response(response)
        await async_regenerate_home_graph_pages(runtime, call.data)
        return response

    async def async_ingest_note(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        await async_sync_home_graph_context(runtime, call.data)
        payload = {
            **_home_graph_payload(runtime, call.data),
            "body": call.data[CONF_NOTE],
        }
        _copy_optional(call.data, payload, CONF_TITLE, "title")
        _copy_optional(call.data, payload, "category", "category")
        _copy_tags_and_private_hosts(call.data, payload, private_hosts=False)
        response = await _call_client(runtime.client.home_graph_ingest_note(payload))
        runtime.async_apply_home_graph_response(response)
        await async_regenerate_home_graph_pages(runtime, call.data)
        return response

    async def async_ingest_artifact(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        await async_sync_home_graph_context(runtime, call.data)
        payload = _home_graph_payload(runtime, call.data)
        for source_key, payload_key in (
            (CONF_ARTIFACT_ID, "artifactId"),
            (CONF_PATH, "path"),
            (CONF_URI, "uri"),
            (CONF_TITLE, "title"),
        ):
            _copy_optional(call.data, payload, source_key, payload_key)
        if CONF_URL in call.data and "uri" not in payload:
            payload["uri"] = call.data[CONF_URL]
        _copy_tags_and_private_hosts(call.data, payload)
        if not any(key in payload for key in ("artifactId", "path", "uri")):
            raise HomeAssistantError(
                "ingest_artifact requires artifact_id, path, uri, or url"
            )
        response = await _call_client(
            runtime.client.home_graph_ingest_artifact(payload)
        )
        runtime.async_apply_home_graph_response(response)
        await async_regenerate_home_graph_pages(runtime, call.data)
        return response

    async def async_link_knowledge(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = _knowledge_link_payload(runtime, call.data)
        response = await _call_client(runtime.client.home_graph_link(payload))
        runtime.async_apply_home_graph_response(response)
        await async_regenerate_home_graph_pages(runtime, call.data)
        return response

    async def async_unlink_knowledge(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = _knowledge_link_payload(runtime, call.data)
        response = await _call_client(runtime.client.home_graph_unlink(payload))
        runtime.async_apply_home_graph_response(response)
        await async_regenerate_home_graph_pages(runtime, call.data)
        return response

    async def async_ask_home_graph(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        if not runtime.home_graph_last_sync_at:
            await async_sync_home_graph_context(runtime, call.data)
        payload = {
            **runtime.home_graph_base_payload(call.data),
            "query": call.data[CONF_QUERY],
            "includeSources": call.data.get(CONF_INCLUDE_SOURCES, True),
            "includeConfidence": call.data.get(CONF_INCLUDE_CONFIDENCE, False),
            "includeLinkedObjects": call.data.get(CONF_INCLUDE_LINKED_OBJECTS, True),
        }
        _copy_optional(call.data, payload, CONF_LIMIT, "limit")
        _copy_optional(call.data, payload, CONF_MODE, "mode")
        response = await _call_client(runtime.client.home_graph_ask(payload))
        runtime.async_apply_home_graph_response(response)
        return response

    async def async_device_passport(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = runtime.home_graph_base_payload(call.data)
        _copy_optional(call.data, payload, CONF_DEVICE_ID, "deviceId")
        if "deviceId" not in payload:
            raise HomeAssistantError("device_passport requires device_id")
        response = await _call_client(
            runtime.client.home_graph_device_passport(payload)
        )
        runtime.async_apply_home_graph_response(response)
        return response

    async def async_room_page(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = runtime.home_graph_base_payload(call.data)
        _copy_optional(call.data, payload, CONF_AREA_ID, "areaId")
        response = await _call_client(runtime.client.home_graph_room_page(payload))
        runtime.async_apply_home_graph_response(response)
        return response

    async def async_home_graph_packet(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = {
            **runtime.home_graph_base_payload(call.data),
            "packetKind": call.data[CONF_PACKET_TYPE],
        }
        _copy_optional(call.data, payload, CONF_AREA_ID, "areaId")
        _copy_optional(call.data, payload, CONF_DEVICE_ID, "deviceId")
        _copy_optional(call.data, payload, CONF_ENTITY_ID, "entityId")
        if metadata := call.data.get("metadata"):
            payload["metadata"] = metadata
        response = await _call_client(runtime.client.home_graph_packet(payload))
        runtime.async_apply_home_graph_response(response)
        return response

    async def async_home_graph_issues(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = runtime.home_graph_base_payload(call.data)
        for key in (CONF_STATUS, CONF_SEVERITY, CONF_CODE, CONF_LIMIT):
            _copy_optional(call.data, payload, key, key)
        response = await _call_client(runtime.client.home_graph_issues(payload))
        runtime.home_graph_issues = response
        async_dispatcher_send(hass, runtime.signal)
        return response

    async def async_review_fact(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = {
            **runtime.home_graph_base_payload(call.data),
            "action": call.data.get("action") or call.data.get(CONF_DECISION),
        }
        if not payload["action"]:
            raise HomeAssistantError("review_fact requires action or decision")
        if issue_id := call.data.get("issue_id") or call.data.get(CONF_FACT_ID):
            payload["issueId"] = issue_id
        _copy_optional(call.data, payload, CONF_NODE_ID, "nodeId")
        _copy_optional(call.data, payload, CONF_SOURCE_ID, "sourceId")
        _copy_optional(call.data, payload, "reviewer", "reviewer")
        if not any(key in payload for key in ("issueId", "nodeId", "sourceId")):
            raise HomeAssistantError(
                "review_fact requires issue_id, node_id, source_id, or fact_id"
            )
        if CONF_VALUE in call.data:
            payload["value"] = call.data[CONF_VALUE]
        response = await _call_client(runtime.client.home_graph_review_fact(payload))
        runtime.async_apply_home_graph_response(response)
        await runtime.async_refresh_home_graph()
        return response

    async def async_home_graph_sources(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = runtime.home_graph_base_payload(call.data)
        _copy_optional(call.data, payload, CONF_LIMIT, "limit")
        response = await _call_client(runtime.client.home_graph_sources(payload))
        runtime.home_graph_sources = response
        async_dispatcher_send(hass, runtime.signal)
        return response

    async def async_home_graph_pages(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = runtime.home_graph_base_payload(call.data)
        _copy_optional(call.data, payload, CONF_LIMIT, "limit")
        if "include_markdown" in call.data:
            payload["includeMarkdown"] = call.data["include_markdown"]
        response = await _call_client(runtime.client.home_graph_pages(payload))
        runtime.home_graph_pages = response
        async_dispatcher_send(hass, runtime.signal)
        return response

    async def async_home_graph_browse(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = runtime.home_graph_base_payload(call.data)
        _copy_optional(call.data, payload, CONF_LIMIT, "limit")
        return await _call_client(runtime.client.home_graph_browse(payload))

    async def async_home_graph_map(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = _map_payload(runtime, call.data)
        return await _call_client(runtime.client.home_graph_map(payload))

    async def async_home_graph_export(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = runtime.home_graph_base_payload(call.data)
        return await _call_client(runtime.client.home_graph_export(payload))

    async def async_home_graph_import(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = {
            **runtime.home_graph_base_payload(call.data),
            "data": call.data["data"],
        }
        response = await _call_client(runtime.client.home_graph_import(payload))
        runtime.async_apply_home_graph_response(response)
        await runtime.async_refresh_home_graph()
        return response

    async def async_home_graph_reset(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = runtime.home_graph_base_payload(call.data)
        dry_run = bool(call.data.get(CONF_DRY_RUN))
        if dry_run:
            payload["dryRun"] = True
        elif call.data.get(CONF_CONFIRM) != "RESET":
            raise HomeAssistantError("Type RESET to reset the Home Graph space.")
        response = await _call_client(runtime.client.home_graph_reset(payload))
        if not dry_run:
            runtime.async_apply_home_graph_response(response)
            await runtime.async_refresh_home_graph()
        return response

    async def async_home_graph_reindex(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime_from_service_call(hass, call)
        payload = runtime.home_graph_base_payload(call.data)
        response = await _call_client(runtime.client.home_graph_reindex(payload))
        runtime.async_apply_home_graph_response(response)
        await runtime.async_refresh_home_graph()
        return response

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
    hass.services.async_register(
        DOMAIN,
        SERVICE_HOME_GRAPH_STATUS,
        async_home_graph_status,
        schema=HOME_GRAPH_COMMON_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC_HOME_GRAPH,
        async_sync_home_graph,
        schema=SYNC_HOME_GRAPH_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_INGEST_URL,
        async_ingest_url,
        schema=INGEST_URL_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_INGEST_NOTE,
        async_ingest_note,
        schema=INGEST_NOTE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_INGEST_ARTIFACT,
        async_ingest_artifact,
        schema=INGEST_ARTIFACT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LINK_KNOWLEDGE,
        async_link_knowledge,
        schema=LINK_KNOWLEDGE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UNLINK_KNOWLEDGE,
        async_unlink_knowledge,
        schema=UNLINK_KNOWLEDGE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ASK_HOME_GRAPH,
        async_ask_home_graph,
        schema=ASK_HOME_GRAPH_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DEVICE_PASSPORT,
        async_device_passport,
        schema=DEVICE_PASSPORT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ROOM_PAGE,
        async_room_page,
        schema=ROOM_PAGE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_HOME_GRAPH_PACKET,
        async_home_graph_packet,
        schema=HOME_GRAPH_PACKET_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_HOME_GRAPH_ISSUES,
        async_home_graph_issues,
        schema=HOME_GRAPH_ISSUES_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REVIEW_FACT,
        async_review_fact,
        schema=REVIEW_FACT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_HOME_GRAPH_SOURCES,
        async_home_graph_sources,
        schema=HOME_GRAPH_LIST_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_HOME_GRAPH_PAGES,
        async_home_graph_pages,
        schema=HOME_GRAPH_PAGES_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_HOME_GRAPH_BROWSE,
        async_home_graph_browse,
        schema=HOME_GRAPH_LIST_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_HOME_GRAPH_MAP,
        async_home_graph_map,
        schema=HOME_GRAPH_MAP_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_HOME_GRAPH_EXPORT,
        async_home_graph_export,
        schema=HOME_GRAPH_COMMON_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_HOME_GRAPH_IMPORT,
        async_home_graph_import,
        schema=HOME_GRAPH_IMPORT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_HOME_GRAPH_RESET,
        async_home_graph_reset,
        schema=HOME_GRAPH_RESET_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_HOME_GRAPH_REINDEX,
        async_home_graph_reindex,
        schema=HOME_GRAPH_REINDEX_SCHEMA,
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
        home_graph_enabled=entry.data.get(
            CONF_HOME_GRAPH_ENABLED, DEFAULT_HOME_GRAPH_ENABLED
        ),
        installation_id=entry.data.get(CONF_INSTALLATION_ID)
        or derive_installation_id(hass, entry),
        knowledge_space_id=entry.data.get(CONF_KNOWLEDGE_SPACE_ID) or None,
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = runtime

    await async_setup_frontend(hass)
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
    if runtime.home_graph_enabled:
        # Scope the auto-sync task to the config entry so Home Assistant cancels
        # it when the entry is unloaded or reloaded; a bare hass.create_task
        # would leak a running sync past the entry's lifetime.
        task_name = f"{DOMAIN}_auto_sync_{entry.entry_id}"
        if getattr(hass, "is_running", False):
            entry.async_create_background_task(
                hass, _async_auto_sync_home_graph(runtime), name=task_name
            )
        else:
            runtime.unsubscribe_auto_sync = hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED,
                lambda _event: entry.async_create_background_task(
                    hass, _async_auto_sync_home_graph(runtime), name=task_name
                ),
            )
    return True


async def _async_auto_sync_home_graph(runtime: GoodVibesRuntimeData) -> None:
    """Refresh the daemon Home Graph in the background after setup."""

    try:
        base_payload = runtime.home_graph_base_payload()
        snapshot = await async_build_home_graph_snapshot(
            runtime.hass,
            runtime.entry,
            base_payload["installationId"],
            base_payload.get("knowledgeSpaceId"),
        )
        response = await runtime.client.home_graph_sync(snapshot)
        runtime.async_apply_home_graph_response(response, sync=True)
        _log_home_graph_sync(snapshot, response, trigger="startup")
        await runtime.async_refresh_home_graph()
    except GoodVibesClientError as err:
        runtime.home_graph_last_error = str(err)
        async_dispatcher_send(runtime.hass, runtime.signal)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a GoodVibes config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime = hass.data[DOMAIN].pop(entry.entry_id, None)
        if runtime and runtime.unsubscribe_event:
            runtime.unsubscribe_event()
        if runtime and runtime.unsubscribe_auto_sync:
            runtime.unsubscribe_auto_sync()
        if not any(
            isinstance(value, GoodVibesRuntimeData)
            for value in hass.data.get(DOMAIN, {}).values()
        ):
            async_unload_frontend_panel(hass)
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


def _log_home_graph_sync(
    snapshot: dict[str, Any],
    response: dict[str, Any],
    *,
    trigger: str,
) -> None:
    """Log a compact Home Graph sync summary for clean rebuild coordination."""

    _LOGGER.info(
        (
            "GoodVibes Home Graph sync completed: trigger=%s installation_id=%s "
            "knowledge_space_id=%s entities=%s devices=%s areas=%s automations=%s "
            "scripts=%s scenes=%s integrations=%s ok=%s sources=%s nodes=%s edges=%s "
            "issues=%s status=%s"
        ),
        trigger,
        snapshot.get("installationId"),
        snapshot.get("knowledgeSpaceId"),
        _count(snapshot.get("entities")),
        _count(snapshot.get("devices")),
        _count(snapshot.get("areas")),
        _count(snapshot.get("automations")),
        _count(snapshot.get("scripts")),
        _count(snapshot.get("scenes")),
        _count(snapshot.get("integrations")),
        response.get("ok"),
        _first_number(response, "sourceCount", "sources"),
        _first_number(response, "nodeCount", "nodes"),
        _first_number(response, "edgeCount", "edges"),
        _first_number(response, "issueCount", "issues"),
        response.get("status"),
    )


def _count(value: Any) -> int:
    """Return a count for list-like or count-bearing payload values."""

    if isinstance(value, list | tuple | set):
        return len(value)
    if isinstance(value, dict):
        count = value.get("count")
        if isinstance(count, int):
            return count
    return 0


def _first_number(payload: dict[str, Any], *keys: str) -> int | None:
    """Return the first numeric count or list length from a payload."""

    for key in keys:
        value = payload.get(key)
        if isinstance(value, int | float):
            return int(value)
        if isinstance(value, list | tuple | set):
            return len(value)
        if isinstance(value, dict):
            count = value.get("count")
            if isinstance(count, int | float):
                return int(count)
    return None


def _async_create_home_graph_issue(
    hass: HomeAssistant,
    issue_id: str,
    translation_key: str,
    placeholders: dict[str, str] | None = None,
) -> None:
    """Create a Home Assistant repair issue for Home Graph."""

    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=translation_key,
        translation_placeholders=placeholders,
    )


def _async_clear_home_graph_issue(hass: HomeAssistant, issue_id: str) -> None:
    """Clear a Home Assistant repair issue for Home Graph."""

    ir.async_delete_issue(hass, DOMAIN, issue_id)


def _home_graph_issue_count(payload: dict[str, Any]) -> int:
    """Return the number of daemon-reported Home Graph issues."""

    issues = payload.get("issues")
    if isinstance(issues, list):
        return len(issues)
    count = payload.get("count")
    return count if isinstance(count, int) else 0


async def _call_client(awaitable) -> dict[str, Any]:
    """Call the daemon client and convert errors for Home Assistant."""

    try:
        return await awaitable
    except GoodVibesClientError as err:
        raise HomeAssistantError(str(err)) from err
