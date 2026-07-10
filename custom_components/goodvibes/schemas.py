"""Voluptuous service schemas for the GoodVibes integration.

Split out of ``__init__.py`` so the service field validation lives beside no
runtime logic. The map filter field lists are owned by ``daemon_payloads`` and
shared with the panel; the schema only iterates their keys.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_AGENT_ID,
    CONF_ALLOW_PRIVATE_HOSTS,
    CONF_AREA_ID,
    CONF_ARTIFACT_ID,
    CONF_CODE,
    CONF_CONFIG_ENTRY_ID,
    CONF_CONFIRM,
    CONF_CONVERSATION_ID,
    CONF_DECISION,
    CONF_DEVICE_ID,
    CONF_DISPLAY_NAME,
    CONF_DRY_RUN,
    CONF_ENTITY_ID,
    CONF_FACT_ID,
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
    CONF_PROPOSAL_ID,
    CONF_PROVIDER_ID,
    CONF_QUERY,
    CONF_RELATION,
    CONF_RUN_ID,
    CONF_SESSION_ID,
    CONF_SEVERITY,
    CONF_SOURCE_ID,
    CONF_STATUS,
    CONF_TAGS,
    CONF_TARGET_ID,
    CONF_TARGET_KIND,
    CONF_TASK,
    CONF_TASK_ID,
    CONF_TITLE,
    CONF_TOOL,
    CONF_TOOLS,
    CONF_URI,
    CONF_URL,
    CONF_USER_ID,
    CONF_VALUE,
    DEFAULT_CONVERSATION_ID,
    DEFAULT_DEVICE_ID,
    DEFAULT_DISPLAY_NAME,
)
from .daemon_payloads import MAP_GENERIC_FIELDS, MAP_HA_FIELDS


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

CAUSAL_CHAIN_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_LIMIT, default=10): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)

HABIT_PROPOSALS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
    }
)

ACCEPT_HABIT_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
        vol.Required(CONF_PROPOSAL_ID): cv.string,
        vol.Optional(CONF_CONFIRM): cv.string,
    }
)
