"""Constants for the GoodVibes integration."""

from __future__ import annotations

DOMAIN = "goodvibes"
INTEGRATION_VERSION = "0.5.68"
UPDATE_REPOSITORY = "mgd34msu/goodvibes-homeassistant"
UPDATE_RELEASES_API_URL = f"https://api.github.com/repos/{UPDATE_REPOSITORY}/releases/latest"
UPDATE_RELEASES_URL = f"https://github.com/{UPDATE_REPOSITORY}/releases"

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
CONF_TOOL = "tool"
CONF_INPUT = "input"
CONF_HOME_GRAPH_ENABLED = "home_graph_enabled"
CONF_INSTALLATION_ID = "installation_id"
CONF_KNOWLEDGE_SPACE_ID = "knowledge_space_id"
CONF_URL = "url"
CONF_URI = "uri"
CONF_NOTE = "note"
CONF_TITLE = "title"
CONF_TAGS = "tags"
CONF_SOURCE_ID = "source_id"
CONF_NODE_ID = "node_id"
CONF_TARGET_KIND = "target_kind"
CONF_TARGET_ID = "target_id"
CONF_RELATION = "relation"
CONF_QUERY = "query"
CONF_INCLUDE_SOURCES = "include_sources"
CONF_INCLUDE_LINKED_OBJECTS = "include_linked_objects"
CONF_INCLUDE_CONFIDENCE = "include_confidence"
CONF_LIMIT = "limit"
CONF_MODE = "mode"
CONF_ARTIFACT_ID = "artifact_id"
CONF_PATH = "path"
CONF_ALLOW_PRIVATE_HOSTS = "allow_private_hosts"
CONF_FACT_ID = "fact_id"
CONF_DECISION = "decision"
CONF_VALUE = "value"
CONF_PACKET_TYPE = "packet_type"
CONF_STATUS = "status"
CONF_SEVERITY = "severity"
CONF_CODE = "code"
CONF_CONFIRM = "confirm"
CONF_DRY_RUN = "dry_run"

DEFAULT_DAEMON_URL = "http://127.0.0.1:3210"
DEFAULT_EVENT_TYPE = "goodvibes_message"
DEFAULT_DEVICE_ID = "goodvibes-daemon"
DEFAULT_DEVICE_NAME = "GoodVibes Daemon"
DEFAULT_CONVERSATION_ID = "home"
DEFAULT_ASSIST_CONVERSATION_PREFIX = "assist"
DEFAULT_DISPLAY_NAME = "Home Assistant"
DEFAULT_CONVERSATION_TIMEOUT_MS = 120000
DEFAULT_HOME_GRAPH_ENABLED = True

PLATFORMS = ["sensor", "conversation", "update"]

SIGNAL_UPDATE = "goodvibes_update"

WEBHOOK_PATH = "/webhook/homeassistant"

ENDPOINT_STATUS = "/status"
ENDPOINT_HEALTH = "/api/homeassistant/health"
ENDPOINT_CONVERSATION = "/api/homeassistant/conversation"
ENDPOINT_CONVERSATION_STREAM = "/api/homeassistant/conversation/stream"
ENDPOINT_CONVERSATION_CANCEL = "/api/homeassistant/conversation/cancel"
ENDPOINT_MANIFEST = "/api/channels/actions/homeassistant/homeassistant-manifest"
ENDPOINT_HOMEASSISTANT_STATUS = (
    "/api/channels/actions/homeassistant/homeassistant-status"
)
ENDPOINT_TOOLS = "/api/channels/tools/homeassistant"
ENDPOINT_AGENT_TOOLS = "/api/channels/agent-tools/homeassistant"
ENDPOINT_HOME_GRAPH_STATUS = "/api/homeassistant/home-graph/status"
ENDPOINT_HOME_GRAPH_SYNC = "/api/homeassistant/home-graph/sync"
ENDPOINT_HOME_GRAPH_INGEST_URL = "/api/homeassistant/home-graph/ingest/url"
ENDPOINT_HOME_GRAPH_INGEST_NOTE = "/api/homeassistant/home-graph/ingest/note"
ENDPOINT_HOME_GRAPH_INGEST_ARTIFACT = "/api/homeassistant/home-graph/ingest/artifact"
ENDPOINT_HOME_GRAPH_LINK = "/api/homeassistant/home-graph/link"
ENDPOINT_HOME_GRAPH_UNLINK = "/api/homeassistant/home-graph/unlink"
ENDPOINT_HOME_GRAPH_ASK = "/api/homeassistant/home-graph/ask"
ENDPOINT_HOME_GRAPH_DEVICE_PASSPORT = (
    "/api/homeassistant/home-graph/device-passport"
)
ENDPOINT_HOME_GRAPH_ROOM_PAGE = "/api/homeassistant/home-graph/room-page"
ENDPOINT_HOME_GRAPH_PACKET = "/api/homeassistant/home-graph/packet"
ENDPOINT_HOME_GRAPH_ISSUES = "/api/homeassistant/home-graph/issues"
ENDPOINT_HOME_GRAPH_FACT_REVIEW = "/api/homeassistant/home-graph/facts/review"
ENDPOINT_HOME_GRAPH_SOURCES = "/api/homeassistant/home-graph/sources"
ENDPOINT_HOME_GRAPH_PAGES = "/api/homeassistant/home-graph/pages"
ENDPOINT_HOME_GRAPH_BROWSE = "/api/homeassistant/home-graph/browse"
ENDPOINT_HOME_GRAPH_MAP = "/api/homeassistant/home-graph/map"
ENDPOINT_HOME_GRAPH_EXPORT = "/api/homeassistant/home-graph/export"
ENDPOINT_HOME_GRAPH_IMPORT = "/api/homeassistant/home-graph/import"
ENDPOINT_HOME_GRAPH_RESET = "/api/homeassistant/home-graph/reset"
ENDPOINT_HOME_GRAPH_REINDEX = "/api/homeassistant/home-graph/reindex"
ENDPOINT_HOME_GRAPH_REFINEMENT_RUN = "/api/homeassistant/home-graph/refinement/run"
ENDPOINT_HOME_GRAPH_REFINEMENT_TASKS = "/api/homeassistant/home-graph/refinement/tasks"

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
