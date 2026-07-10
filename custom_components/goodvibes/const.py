"""Constants for the GoodVibes integration."""

from __future__ import annotations

DOMAIN = "goodvibes"
INTEGRATION_VERSION = "0.6.5"

# The integration always targets the LATEST published @pellux/goodvibes-sdk; it
# is a thin client over stable daemon HTTP routes, not a pinned SDK build. This
# records the newest npm version the daemon contract was last validated against
# (see docs/sdk-compatibility.md). CI echoes the live npm version against this
# label as an informational nudge when the two drift.
SDK_PACKAGE = "@pellux/goodvibes-sdk"
SDK_VALIDATED_VERSION = "1.6.1"

# The daemon HTTP contract this client is written against. At connect the client
# reads the daemon's advertised software version (GET /status -> version) and
# the Home Assistant surface capabilities (GET /api/homeassistant/health ->
# capabilities) and compares them against these declarations, raising a Home
# Assistant repair issue when the daemon is older than the minimum this client
# needs or is missing a surface capability it relies on. MIN_DAEMON_VERSION is
# the oldest daemon whose Home Assistant surface speaks the contract this
# integration depends on: the streaming conversation delta frames landed in SDK
# 1.3.0, so that is the floor.
MIN_DAEMON_VERSION = "1.3.0"
REQUIRED_DAEMON_CAPABILITIES = ("conversation-stream", "conversation-cancel")
ISSUE_DAEMON_VERSION = "daemon_version_unsupported"
ISSUE_DAEMON_CAPABILITIES = "daemon_capabilities_missing"

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
CONF_INCLUDE_UNEXPOSED_ENTITIES = "include_unexposed_entities"
# Conversation options (options flow). CONF_LLM_HASS_API reuses Home Assistant's
# own option key ("llm_hass_api") so the selected Assist LLM API is stored the
# same way first-class conversation agents store it.
CONF_PROMPT = "prompt"
# Perception-trigger options (options flow). Off by default; when enabled, state
# changes of the selected entities start an attributed daemon session.
CONF_PERCEPTION_ENABLED = "perception_enabled"
CONF_PERCEPTION_ENTITIES = "perception_entities"
CONF_PERCEPTION_PROMPT = "perception_prompt"
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

DEFAULT_DAEMON_URL = "http://127.0.0.1:3421"
DEFAULT_EVENT_TYPE = "goodvibes_message"
DEFAULT_DEVICE_ID = "goodvibes-daemon"
DEFAULT_DEVICE_NAME = "GoodVibes Daemon"
DEFAULT_CONVERSATION_ID = "home"
DEFAULT_ASSIST_CONVERSATION_PREFIX = "assist"
DEFAULT_DISPLAY_NAME = "Home Assistant"
DEFAULT_CONVERSATION_TIMEOUT_MS = 120000
DEFAULT_HOME_GRAPH_ENABLED = True
# Perception triggers are opt-in and start disabled. When enabled with no
# custom instruction, this default frames the attributed session.
DEFAULT_PERCEPTION_ENABLED = False
DEFAULT_PERCEPTION_PROMPT = (
    "A Home Assistant entity you observe changed state. Review the change and "
    "take any helpful action that is within your allowed tools."
)
# Minimum seconds between attributed sessions started for the same entity, so a
# chattering sensor cannot spawn a flood of daemon sessions.
PERCEPTION_MIN_INTERVAL_S = 10.0
DEFAULT_PERCEPTION_DISPLAY_NAME = "GoodVibes Perception"
DEFAULT_PERCEPTION_CONVERSATION_PREFIX = "perception"
# By default the Home Graph snapshot only carries entities the user has exposed
# to assistants (the same boundary Home Assistant's own voice and conversation
# agents respect). Set the config toggle to include everything in the registry.
DEFAULT_INCLUDE_UNEXPOSED_ENTITIES = False

# Largest browser upload the panel proxy will buffer to local disk before
# forwarding it to the daemon. This matches the daemon's own default artifact
# cap (storage.artifacts.maxBytes, 512 MiB) so the integration refuses an
# oversized file up front instead of filling the temp filesystem first.
MAX_UPLOAD_BYTES = 512 * 1024 * 1024

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
