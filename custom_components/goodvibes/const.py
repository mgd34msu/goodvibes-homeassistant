"""Constants for the GoodVibes integration."""

from __future__ import annotations

DOMAIN = "goodvibes"

CONF_DAEMON_URL = "daemon_url"
CONF_DAEMON_TOKEN = "daemon_token"
CONF_CONFIG_ENTRY_ID = "config_entry_id"
CONF_WEBHOOK_SECRET = "webhook_secret"
CONF_EVENT_TYPE = "event_type"
CONF_CONVERSATION_ID = "conversation_id"
CONF_DEVICE_ID = "device_id"
CONF_ENTITY_ID = "entity_id"
CONF_AREA_ID = "area_id"
CONF_USER_ID = "user_id"
CONF_DISPLAY_NAME = "display_name"
CONF_MESSAGE_ID = "message_id"
CONF_PROVIDER_ID = "provider_id"
CONF_MODEL_ID = "model_id"
CONF_TOOLS = "tools"
CONF_TASK = "task"
CONF_AGENT_ID = "agent_id"
CONF_RUN_ID = "run_id"
CONF_TASK_ID = "task_id"
CONF_SESSION_ID = "session_id"
CONF_INPUT_ID = "input_id"
CONF_TOOL = "tool"
CONF_INPUT = "input"

DEFAULT_DAEMON_URL = "http://127.0.0.1:3210"
DEFAULT_EVENT_TYPE = "goodvibes_message"
DEFAULT_DEVICE_ID = "goodvibes-daemon"
DEFAULT_DEVICE_NAME = "GoodVibes Daemon"
DEFAULT_CONVERSATION_ID = "home"
DEFAULT_DISPLAY_NAME = "Home Assistant"

PLATFORMS = ["sensor"]

SIGNAL_UPDATE = "goodvibes_update"

WEBHOOK_PATH = "/webhook/homeassistant"

ENDPOINT_STATUS = "/status"
ENDPOINT_MANIFEST = "/api/channels/actions/homeassistant/homeassistant-manifest"
ENDPOINT_HOMEASSISTANT_STATUS = (
    "/api/channels/actions/homeassistant/homeassistant-status"
)
ENDPOINT_TOOLS = "/api/channels/tools/homeassistant"
ENDPOINT_AGENT_TOOLS = "/api/channels/agent-tools/homeassistant"

TOOL_NAME_TO_ID = {
    "homeassistant_manifest": "homeassistant:manifest",
    "homeassistant_status": "homeassistant:status",
    "homeassistant_states": "homeassistant:states",
    "homeassistant_state": "homeassistant:state",
    "homeassistant_services": "homeassistant:services",
    "homeassistant_call_service": "homeassistant:call_service",
    "homeassistant_fire_event": "homeassistant:fire_event",
    "homeassistant_render_template": "homeassistant:render_template",
}

TERMINAL_STATUSES = {
    "complete",
    "completed",
    "done",
    "error",
    "failed",
    "cancelled",
    "canceled",
}
