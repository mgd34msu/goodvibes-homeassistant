"""Constants for the GoodVibes integration."""

from __future__ import annotations

from .generated_client import OPERATOR_ROUTES

DOMAIN = "goodvibes"
INTEGRATION_VERSION = "0.10.1"

# The integration always targets the LATEST published @pellux/goodvibes-sdk; it
# is a thin client over stable daemon HTTP routes, not a pinned SDK build. This
# records the newest npm version the daemon contract was last validated against
# (see docs/sdk-compatibility.md). CI echoes the live npm version against this
# label as an informational nudge when the two drift.
#
# Kept as a hand-set literal, not read from generated_client.CONTRACT_VERSION:
# the two coincide today but mean different things (CONTRACT_VERSION is what
# the *mechanical* REST subset was generated against; this label attests a
# human re-ran the docs/sdk-compatibility.md checklist, which also covers
# hand-written surfaces the generated client does not). See
# test_version_check.py::test_contract_version_is_at_least_min_daemon_version
# for the one place this pin is actually checked against CONTRACT_VERSION.
SDK_PACKAGE = "@pellux/goodvibes-sdk"
SDK_VALIDATED_VERSION = "1.10.1"

# The daemon HTTP contract this client is written against. At connect the client
# reads the daemon's advertised software version (GET /status -> version) and
# the Home Assistant surface capabilities (GET /api/homeassistant/health ->
# capabilities) and compares them against these declarations, raising a Home
# Assistant repair issue when the daemon is older than the minimum this client
# needs or is missing a surface capability it relies on. MIN_DAEMON_VERSION is
# the oldest daemon whose Home Assistant surface speaks the contract this
# integration depends on: the streaming conversation delta frames landed in SDK
# 1.3.0, so that is the floor. Conversation streaming is hand-written (not an
# operator method — see generated_client.py's header), so this floor stays
# hand-maintained for the same reason as SDK_VALIDATED_VERSION above.
MIN_DAEMON_VERSION = "1.3.0"
REQUIRED_DAEMON_CAPABILITIES = ("conversation-stream", "conversation-cancel")
ISSUE_DAEMON_VERSION = "daemon_version_unsupported"
ISSUE_DAEMON_CAPABILITIES = "daemon_capabilities_missing"
# Raised while the daemon cannot be reached at all (connection refused, timed
# out) as distinct from ISSUE_DAEMON_VERSION/ISSUE_DAEMON_CAPABILITIES, which
# mean the daemon answered but fails the contract. Cleared the moment a probe
# reaches the daemon again, whether or not the contract then passes.
ISSUE_DAEMON_UNREACHABLE = "daemon_unreachable"

# The daemon-connection watchdog (data.GoodVibesRuntimeData) retries an
# unreachable or contract-incompatible daemon on an exponential backoff that
# starts here and never gives up, so the integration recovers on its own
# instead of waiting for Home Assistant to restart.
RECONNECT_INITIAL_DELAY_S = 1.0
RECONNECT_MAX_DELAY_S = 60.0

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
# Consent-gated habit mining (options flow). Off by default; when enabled, the
# integration analyzes its own observation history locally and surfaces recurring
# patterns as automation PROPOSALS for the user to review. Nothing is created
# silently and no observation data leaves the machine.
CONF_HABIT_MINING_ENABLED = "habit_mining_enabled"
CONF_HABIT_RETENTION_DAYS = "habit_retention_days"
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
CONF_PROPOSAL_ID = "proposal_id"

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
# Causal provenance. The integration tracks the Home Assistant context chain
# (context.id / parent_id / user_id) that links a state change to its cause: an
# automation run, a script, a scene, a service call, or a user. These are the
# Home Assistant bus event types whose context identifies a triggering cause; a
# state change's context is walked back through these to attribute the cause.
EVENT_AUTOMATION_TRIGGERED = "automation_triggered"
EVENT_SCRIPT_STARTED = "script_started"
# Bound the in-memory causal indexes so a busy home cannot grow them without
# limit. These are recent-history caches, not a full audit log.
PROVENANCE_MAX_CAUSES = 1024
PROVENANCE_MAX_CHANGES = 2048
PROVENANCE_MAX_CHANGES_PER_ENTITY = 25
PROVENANCE_CHAIN_MAX_DEPTH = 12

# Consent-gated habit mining defaults and honest retention bounds. Observations
# live in memory only, capped by both age (retention days) and count.
DEFAULT_HABIT_MINING_ENABLED = False
DEFAULT_HABIT_RETENTION_DAYS = 14
HABIT_RETENTION_DAYS_MIN = 1
HABIT_RETENTION_DAYS_MAX = 60
HABIT_MAX_OBSERVATIONS = 20000
# A pattern is proposed only when it recurs on at least this many distinct days
# and this many total times inside the retained window.
HABIT_MIN_DISTINCT_DAYS = 3
HABIT_MIN_OCCURRENCES = 3
# Width of the time-of-day bucket a recurring change is grouped into, in minutes.
HABIT_TIME_BUCKET_MINUTES = 30
# How often the local analysis runs while habit mining is enabled.
HABIT_ANALYSIS_INTERVAL_MINUTES = 180

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

# Hand-written: not operator methods (see generated_client.py's header).
ENDPOINT_HEALTH = "/api/homeassistant/health"
ENDPOINT_CONVERSATION = "/api/homeassistant/conversation"
ENDPOINT_CONVERSATION_STREAM = "/api/homeassistant/conversation/stream"
ENDPOINT_CONVERSATION_CANCEL = "/api/homeassistant/conversation/cancel"

# Every constant below is an operator method this client consumes, so its path
# is read from the vendored generated client (OPERATOR_ROUTES) instead of
# being hand-typed. {surface}/{actionId}/{toolId} are filled with the one
# Home Assistant surface value this integration uses.
ENDPOINT_STATUS = OPERATOR_ROUTES["control.status"].path
ENDPOINT_MANIFEST = OPERATOR_ROUTES["channels.actions.invoke"].path.format(surface="homeassistant", actionId="homeassistant-manifest")
ENDPOINT_HOMEASSISTANT_STATUS = OPERATOR_ROUTES["channels.actions.invoke"].path.format(surface="homeassistant", actionId="homeassistant-status")
ENDPOINT_TOOLS = OPERATOR_ROUTES["channels.tools.surface.list"].path.format(surface="homeassistant")
ENDPOINT_AGENT_TOOLS = OPERATOR_ROUTES["channels.agent_tools.surface.list"].path.format(surface="homeassistant")
ENDPOINT_HOME_GRAPH_STATUS = OPERATOR_ROUTES["homeassistant.homeGraph.status"].path
ENDPOINT_HOME_GRAPH_SYNC = OPERATOR_ROUTES["homeassistant.homeGraph.syncHomeGraph"].path
ENDPOINT_HOME_GRAPH_INGEST_URL = OPERATOR_ROUTES["homeassistant.homeGraph.ingestHomeGraphUrl"].path
ENDPOINT_HOME_GRAPH_INGEST_NOTE = OPERATOR_ROUTES["homeassistant.homeGraph.ingestHomeGraphNote"].path
ENDPOINT_HOME_GRAPH_INGEST_ARTIFACT = OPERATOR_ROUTES["homeassistant.homeGraph.ingestHomeGraphArtifact"].path
ENDPOINT_HOME_GRAPH_LINK = OPERATOR_ROUTES["homeassistant.homeGraph.linkHomeGraphKnowledge"].path
ENDPOINT_HOME_GRAPH_UNLINK = OPERATOR_ROUTES["homeassistant.homeGraph.unlinkHomeGraphKnowledge"].path
ENDPOINT_HOME_GRAPH_ASK = OPERATOR_ROUTES["homeassistant.homeGraph.askHomeGraph"].path
ENDPOINT_HOME_GRAPH_DEVICE_PASSPORT = OPERATOR_ROUTES["homeassistant.homeGraph.refreshDevicePassport"].path
ENDPOINT_HOME_GRAPH_ROOM_PAGE = OPERATOR_ROUTES["homeassistant.homeGraph.generateRoomPage"].path
ENDPOINT_HOME_GRAPH_PACKET = OPERATOR_ROUTES["homeassistant.homeGraph.generateHomeGraphPacket"].path
ENDPOINT_HOME_GRAPH_ISSUES = OPERATOR_ROUTES["homeassistant.homeGraph.listHomeGraphIssues"].path
ENDPOINT_HOME_GRAPH_FACT_REVIEW = OPERATOR_ROUTES["homeassistant.homeGraph.reviewHomeGraphFact"].path
ENDPOINT_HOME_GRAPH_SOURCES = OPERATOR_ROUTES["homeassistant.homeGraph.sources.list"].path
ENDPOINT_HOME_GRAPH_PAGES = OPERATOR_ROUTES["homeassistant.homeGraph.pages.list"].path
ENDPOINT_HOME_GRAPH_BROWSE = OPERATOR_ROUTES["homeassistant.homeGraph.browse"].path
ENDPOINT_HOME_GRAPH_MAP = OPERATOR_ROUTES["homeassistant.homeGraph.map"].path
ENDPOINT_HOME_GRAPH_EXPORT = OPERATOR_ROUTES["homeassistant.homeGraph.export"].path
ENDPOINT_HOME_GRAPH_IMPORT = OPERATOR_ROUTES["homeassistant.homeGraph.import"].path
ENDPOINT_HOME_GRAPH_RESET = OPERATOR_ROUTES["homeassistant.homeGraph.reset"].path
ENDPOINT_HOME_GRAPH_REINDEX = OPERATOR_ROUTES["homeassistant.homeGraph.reindex"].path
ENDPOINT_HOME_GRAPH_REFINEMENT_RUN = OPERATOR_ROUTES["homeassistant.homeGraph.refinement.run"].path
ENDPOINT_HOME_GRAPH_REFINEMENT_TASKS = OPERATOR_ROUTES["homeassistant.homeGraph.refinement.tasks.list"].path

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

ISSUE_HABIT_PROPOSALS = "habit_proposals_available"

TERMINAL_STATUSES = {
    "complete",
    "completed",
    "done",
    "error",
    "failed",
    "cancelled",
    "canceled",
}
