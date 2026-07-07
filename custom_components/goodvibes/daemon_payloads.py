"""Shared daemon payload builders for services and the Home panel.

Both the Home Assistant services (snake_case fields validated by voluptuous) and
the sidebar panel/upload proxy (camelCase fields from the browser) send the same
daemon Home Graph contract. This module is the single place that maps either
input convention onto that contract, so the two call sites can no longer drift
apart. Every builder tolerates both snake_case and camelCase source keys.

The ``runtime`` argument is a ``GoodVibesRuntimeData`` (typed ``Any`` here to keep
this module free of an import cycle with the package root); the builders only use
``runtime.home_graph_base_payload(...)`` and ``runtime.home_graph_enabled``.
"""

from __future__ import annotations

import json
from typing import Any

from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_ALLOW_PRIVATE_HOSTS,
    CONF_ARTIFACT_ID,
    CONF_AREA_ID,
    CONF_CONVERSATION_ID,
    CONF_DEVICE_ID,
    CONF_DISPLAY_NAME,
    CONF_ENTITY_ID,
    CONF_INSTALLATION_ID,
    CONF_KNOWLEDGE_SPACE_ID,
    CONF_LIMIT,
    CONF_MESSAGE_ID,
    CONF_MODEL_ID,
    CONF_NODE_ID,
    CONF_PATH,
    CONF_PROVIDER_ID,
    CONF_QUERY,
    CONF_RELATION,
    CONF_SOURCE_ID,
    CONF_TAGS,
    CONF_TARGET_ID,
    CONF_TARGET_KIND,
    CONF_TITLE,
    CONF_TOOLS,
    CONF_URI,
    CONF_URL,
    CONF_USER_ID,
    DEFAULT_CONVERSATION_ID,
    DEFAULT_DEVICE_ID,
    DEFAULT_DISPLAY_NAME,
)

# Canonical snake_case service key -> camelCase daemon key for the Home Graph
# map filter fields. The panel sends the camelCase form directly; services send
# the snake_case form. The map builder accepts either for every field.
MAP_GENERIC_FIELDS: dict[str, str] = {
    "record_kinds": "recordKinds",
    "ids": "ids",
    "linked_to_ids": "linkedToIds",
    "node_kinds": "nodeKinds",
    "source_types": "sourceTypes",
    "source_statuses": "sourceStatuses",
    "node_statuses": "nodeStatuses",
    "issue_codes": "issueCodes",
    "issue_statuses": "issueStatuses",
    "issue_severities": "issueSeverities",
    "edge_relations": "edgeRelations",
    CONF_TAGS: "tags",
}
MAP_HA_FIELDS: dict[str, str] = {
    "object_kinds": "objectKinds",
    "entity_ids": "entityIds",
    "device_ids": "deviceIds",
    "area_ids": "areaIds",
    "integration_ids": "integrationIds",
    "integration_domains": "integrationDomains",
    "domains": "domains",
    "device_classes": "deviceClasses",
    "labels": "labels",
}


# --- pure value helpers -----------------------------------------------------


def first_value(data: dict[str, Any], *names: str, default: Any = None) -> Any:
    """Return the first non-empty value across snake_case/camelCase aliases."""

    for name in names:
        value = data.get(name)
        if value not in (None, ""):
            return value
    return default


def truthy(value: Any) -> bool:
    """Return a form-friendly boolean (accepts "1"/"true"/"yes"/"on")."""

    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_jsonish(value: Any) -> Any:
    """Parse JSON supplied as a string while accepting native objects."""

    if value in (None, ""):
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return value


def parse_jsonish_or_text(value: Any) -> Any:
    """Parse JSON when possible, otherwise preserve the original text."""

    try:
        return parse_jsonish(value)
    except ValueError:
        return value


def string_list(value: Any) -> list[str]:
    """Parse list-like values into a stable list of unique non-empty strings."""

    if value in (None, ""):
        return []
    parsed = parse_jsonish_or_text(value)
    if isinstance(parsed, str):
        items: Any = parsed.split(",")
    elif isinstance(parsed, (list, tuple, set)):
        items = parsed
    else:
        items = [parsed]
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def string_set(value: Any) -> set[str]:
    """Parse list-like values into a set of non-empty strings."""

    if value in (None, ""):
        return set()
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value if item not in (None, "") and str(item)}
    return {str(value)}


def parse_tags(value: Any) -> list[str] | None:
    """Parse tags from JSON arrays, native lists, or comma-separated strings."""

    if value in (None, ""):
        return None
    parsed = (
        parse_jsonish(value)
        if isinstance(value, str) and value.strip().startswith("[")
        else value
    )
    if isinstance(parsed, list):
        tags = [str(item).strip() for item in parsed if str(item).strip()]
    else:
        tags = [item.strip() for item in str(parsed).split(",") if item.strip()]
    return tags or None


def camel_key(value: str) -> str:
    """Convert a small snake_case key to camelCase."""

    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def required_text(data: dict[str, Any], *names: str) -> str:
    """Return a required text field or raise if none of the aliases are set."""

    value = first_value(data, *names)
    if value in (None, ""):
        raise HomeAssistantError(f"Missing required field: {names[0]}")
    return str(value)


def required_object(data: dict[str, Any], name: str) -> dict[str, Any]:
    """Return a required object field or raise if it is not a dict."""

    value = data.get(name)
    if not isinstance(value, dict):
        raise HomeAssistantError(f"Missing required object field: {name}")
    return value


def copy_optional(
    source: dict[str, Any],
    target: dict[str, Any],
    source_key: str,
    target_key: str,
) -> None:
    """Copy a single non-empty source field into a daemon payload."""

    if (value := source.get(source_key)) not in (None, ""):
        target[target_key] = value


def copy_optional_any(
    source: dict[str, Any],
    target: dict[str, Any],
    source_keys: tuple[str, ...],
    target_key: str,
) -> None:
    """Copy the first non-empty aliased source field into a payload."""

    value = first_value(source, *source_keys)
    if value not in (None, ""):
        target[target_key] = value


def copy_optional_list(
    source: dict[str, Any],
    target: dict[str, Any],
    source_key: str,
    target_key: str,
) -> None:
    """Copy a non-empty list-like source field into a payload as a list."""

    values = string_list(source.get(source_key))
    if values:
        target[target_key] = values


def copy_tags_and_private_hosts(
    data: dict[str, Any],
    payload: dict[str, Any],
    *,
    private_hosts: bool = True,
) -> None:
    """Copy Home Graph ingest tags and the remote-fetch policy flag."""

    if tags := parse_tags(first_value(data, CONF_TAGS, "tags")):
        payload["tags"] = tags
    if private_hosts and (
        CONF_ALLOW_PRIVATE_HOSTS in data or "allowPrivateHosts" in data
    ):
        payload["allowPrivateHosts"] = truthy(
            first_value(data, CONF_ALLOW_PRIVATE_HOSTS, "allowPrivateHosts")
        )


def ensure_home_graph_enabled(runtime: Any) -> None:
    """Raise if Home Graph is disabled for this config entry."""

    if not runtime.home_graph_enabled:
        raise HomeAssistantError("Home Graph is disabled for this GoodVibes entry")


# --- runtime-aware payload builders -----------------------------------------


def base_payload(runtime: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Build a Home Graph base payload from snake_case or camelCase fields."""

    base_data = {
        CONF_INSTALLATION_ID: first_value(data, CONF_INSTALLATION_ID, "installationId"),
        CONF_KNOWLEDGE_SPACE_ID: first_value(
            data, CONF_KNOWLEDGE_SPACE_ID, "knowledgeSpaceId"
        ),
    }
    return runtime.home_graph_base_payload(base_data)


def target_payload(data: dict[str, Any]) -> dict[str, Any] | None:
    """Return an optional Home Graph target object.

    Accepts an explicit ``target`` object, or a target built from kind/id (plus
    optional relation and title). Kind and id must be provided together.
    """

    explicit = parse_jsonish(data.get("target"))
    if isinstance(explicit, dict):
        return explicit
    target_kind = first_value(data, CONF_TARGET_KIND, "targetKind", "kind")
    target_id = first_value(data, CONF_TARGET_ID, "targetId", "target_id", "id")
    relation = first_value(data, CONF_RELATION, "relation")
    title = first_value(data, CONF_TITLE, "targetTitle", "target_title")
    if not target_kind and not target_id:
        return None
    if not target_kind or not target_id:
        raise HomeAssistantError("Target kind and target id must be provided together")
    target = {"kind": str(target_kind), "id": str(target_id)}
    if relation:
        target["relation"] = str(relation)
    if title:
        target["title"] = str(title)
    return target


def home_graph_payload(runtime: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Build a Home Graph payload with optional target and metadata."""

    ensure_home_graph_enabled(runtime)
    payload = base_payload(runtime, data)
    if target := target_payload(data):
        payload["target"] = target
    if metadata := parse_jsonish(data.get("metadata")):
        payload["metadata"] = metadata
    return payload


def artifact_payload(runtime: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Build an artifact ingest payload (by artifact id, path, or uri)."""

    payload = home_graph_payload(runtime, data)
    copy_optional_any(data, payload, (CONF_ARTIFACT_ID, "artifactId"), "artifactId")
    copy_optional_any(data, payload, (CONF_PATH, "path"), "path")
    copy_optional_any(data, payload, (CONF_URI, "uri", CONF_URL, "url"), "uri")
    copy_optional_any(data, payload, (CONF_TITLE, "title"), "title")
    copy_tags_and_private_hosts(data, payload)
    if not any(key in payload for key in ("artifactId", "path", "uri")):
        raise HomeAssistantError("Artifact ingest requires artifact_id, path, or uri")
    return payload


def link_payload(runtime: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Build a Home Graph link or unlink payload."""

    ensure_home_graph_enabled(runtime)
    payload = base_payload(runtime, data)
    copy_optional_any(data, payload, (CONF_SOURCE_ID, "sourceId"), "sourceId")
    copy_optional_any(data, payload, (CONF_NODE_ID, "nodeId"), "nodeId")
    if "sourceId" not in payload and "nodeId" not in payload:
        raise HomeAssistantError("Linking requires source_id or node_id")
    target = target_payload(data)
    if target is None:
        raise HomeAssistantError("Linking requires a target kind and id")
    payload["target"] = target
    if metadata := parse_jsonish(data.get("metadata")):
        payload["metadata"] = metadata
    return payload


def review_payload(runtime: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Build a Home Graph fact-review payload."""

    payload = {
        **base_payload(runtime, data),
        "action": required_text(data, "action", "decision"),
    }
    copy_optional_any(data, payload, ("issueId", "issue_id", "fact_id"), "issueId")
    copy_optional_any(data, payload, (CONF_NODE_ID, "nodeId"), "nodeId")
    copy_optional_any(data, payload, (CONF_SOURCE_ID, "sourceId"), "sourceId")
    copy_optional_any(data, payload, ("reviewer",), "reviewer")
    if (
        "issueId" not in payload
        and "nodeId" not in payload
        and "sourceId" not in payload
    ):
        raise HomeAssistantError("Review requires issue_id, node_id, or source_id")
    value = parse_jsonish_or_text(data.get("value"))
    if value is not None:
        payload["value"] = value
    return payload


def query_payload(
    runtime: Any,
    data: dict[str, Any],
    allowed: set[str],
) -> dict[str, Any]:
    """Build a query payload with allowed scalar filter fields."""

    payload = base_payload(runtime, data)
    for key, value in data.items():
        if (
            key in allowed
            and isinstance(value, (str, int, float, bool))
            and value != ""
        ):
            payload[key] = coerce_query_value(key, value)
    return payload


def coerce_query_value(
    key: str,
    value: str | int | float | bool,
) -> str | int | float | bool:
    """Coerce known query scalars to the daemon contract shape."""

    if key in {CONF_LIMIT, "limit"}:
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return value
    return value


def map_payload(runtime: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Build a daemon-side Home Graph map payload with SDK-owned filters.

    Accepts service snake_case fields, panel camelCase fields, and a nested
    ``ha`` object for the Home-Assistant-scoped filters.
    """

    payload = base_payload(runtime, data)
    value = first_value(data, CONF_LIMIT, "limit")
    if value not in (None, ""):
        try:
            payload["limit"] = max(1, int(value))
        except (TypeError, ValueError):
            payload["limit"] = value
    if query := first_value(data, CONF_QUERY, "query"):
        payload["query"] = str(query)
    value = first_value(data, "min_confidence", "minConfidence")
    if value not in (None, ""):
        try:
            payload["minConfidence"] = float(value)
        except (TypeError, ValueError):
            payload["minConfidence"] = value
    for source_keys, target_key in (
        (("include_sources", "includeSources"), "includeSources"),
        (("include_issues", "includeIssues"), "includeIssues"),
        (("include_generated", "includeGenerated"), "includeGenerated"),
    ):
        present = next((key for key in source_keys if key in data), None)
        if present is not None:
            payload[target_key] = truthy(data[present])

    filters = data.get("filters")
    if isinstance(filters, dict):
        payload["filters"] = filters
    for snake_key, camel_key_name in MAP_GENERIC_FIELDS.items():
        values = string_list(first_value(data, snake_key, camel_key_name))
        if values:
            payload[camel_key_name] = values

    ha_payload: dict[str, Any] = {}
    ha = data.get("ha")
    for snake_key, camel_key_name in MAP_HA_FIELDS.items():
        source: Any = None
        if isinstance(ha, dict):
            source = first_value(ha, snake_key, camel_key_name)
        if source in (None, ""):
            source = first_value(data, snake_key, camel_key_name)
        values = string_list(source)
        if values:
            ha_payload[camel_key_name] = values
    if ha_payload:
        payload["ha"] = ha_payload
    return payload


def prompt_payload(
    data: dict[str, Any], *, message_key: str, body_type: str
) -> dict[str, Any]:
    """Build the canonical daemon webhook prompt/agent payload."""

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
