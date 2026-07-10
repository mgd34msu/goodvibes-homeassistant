"""Home Assistant service handlers for the GoodVibes integration.

These 26 services were previously defined as closures inside ``async_setup``;
they now live at module level (Home Assistant's ``services.py`` convention) so
each one can be unit tested in isolation. ``async_setup_services`` registers
them once for the whole Home Assistant instance.

Each handler resolves its target config-entry runtime with
``_runtime_from_service_call(call.hass, call)`` and reuses the shared daemon
payload builders in ``daemon_payloads``.

Authorization
-------------
Every handler that submits work to the daemon, controls a running turn, or
writes/rebuilds/destroys the Home Graph verifies the calling user with
``_async_verify_admin`` before acting. When a call carries a user context whose
user is not an administrator, that helper raises ``Unauthorized``. Calls with no
user context (automations, scripts, and other trusted internal callers) are
allowed through, matching how Home Assistant core treats admin-only services.
Read-only query handlers stay open on purpose so dashboards and non-admin users
can inspect state. ``home_graph_packet`` additionally accepts an entity id, so it
checks the calling user's per-entity control permission for that entity.

    Service              Authorization  Reason
    -------------------  -------------  ---------------------------------------
    prompt               admin          Submits a chat turn to the daemon
    run_agent            admin          Starts an autonomous agent run
    cancel               admin          Cancels a running turn/agent/task
    call_tool            admin          Invokes an arbitrary daemon tool
    sync_home_graph      admin          Uploads a home snapshot to the daemon
    ingest_url           admin          Writes a source into the Home Graph
    ingest_note          admin          Writes a note into the Home Graph
    ingest_artifact      admin          Writes an artifact into the Home Graph
    link_knowledge       admin          Creates a Home Graph link
    unlink_knowledge     admin          Removes a Home Graph link
    review_fact          admin          Records a fact-review decision
    device_passport      admin          Generates/refreshes a device passport
    room_page            admin          Generates/refreshes a room page
    home_graph_packet    admin+entity   Generates a packet; may target an entity
    home_graph_import    admin          Imports a Home Graph space
    home_graph_reset     admin          Destroys a Home Graph space
    home_graph_reindex   admin          Rebuilds the Home Graph index
    status               open (read)    Reports daemon/turn status
    home_graph_status    open (read)    Reports Home Graph status
    ask_home_graph       open (read)    Queries the Home Graph
    home_graph_issues    open (read)    Lists Home Graph issues
    home_graph_sources   open (read)    Lists Home Graph sources
    home_graph_pages     open (read)    Lists Home Graph pages
    home_graph_browse    open (read)    Browses the Home Graph
    home_graph_map       open (read)    Reads the Home Graph map
    home_graph_export    open (read)    Exports a Home Graph space
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from homeassistant.auth.permissions.const import POLICY_CONTROL
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, Unauthorized, UnknownUser
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .client import GoodVibesClientError
from .const import (
    CONF_AGENT_ID,
    CONF_AREA_ID,
    CONF_ARTIFACT_ID,
    CONF_CODE,
    CONF_CONFIG_ENTRY_ID,
    CONF_CONFIRM,
    CONF_DECISION,
    CONF_DEVICE_ID,
    CONF_DRY_RUN,
    CONF_ENTITY_ID,
    CONF_FACT_ID,
    CONF_INCLUDE_CONFIDENCE,
    CONF_INCLUDE_LINKED_OBJECTS,
    CONF_INCLUDE_SOURCES,
    CONF_INPUT,
    CONF_LIMIT,
    CONF_MESSAGE_ID,
    CONF_MODE,
    CONF_NODE_ID,
    CONF_NOTE,
    CONF_PACKET_TYPE,
    CONF_PATH,
    CONF_QUERY,
    CONF_RUN_ID,
    CONF_SESSION_ID,
    CONF_SEVERITY,
    CONF_SOURCE_ID,
    CONF_STATUS,
    CONF_TASK,
    CONF_TASK_ID,
    CONF_TITLE,
    CONF_TOOL,
    CONF_URI,
    CONF_URL,
    CONF_VALUE,
    DOMAIN,
)
from .daemon_payloads import (
    copy_optional as _copy_optional,
    copy_tags_and_private_hosts as _copy_tags_and_private_hosts,
    ensure_home_graph_enabled as _ensure_home_graph_enabled,
    home_graph_payload as _home_graph_payload,
    link_payload as _knowledge_link_payload,
    map_payload as _map_payload,
    prompt_payload as _prompt_payload,
)
from .data import GoodVibesRuntimeData
from .home_graph import async_build_home_graph_snapshot
from .schemas import (
    ASK_HOME_GRAPH_SCHEMA,
    CALL_TOOL_SCHEMA,
    CANCEL_SCHEMA,
    DEVICE_PASSPORT_SCHEMA,
    HOME_GRAPH_COMMON_SCHEMA,
    HOME_GRAPH_IMPORT_SCHEMA,
    HOME_GRAPH_ISSUES_SCHEMA,
    HOME_GRAPH_LIST_SCHEMA,
    HOME_GRAPH_MAP_SCHEMA,
    HOME_GRAPH_PACKET_SCHEMA,
    HOME_GRAPH_PAGES_SCHEMA,
    HOME_GRAPH_REINDEX_SCHEMA,
    HOME_GRAPH_RESET_SCHEMA,
    INGEST_ARTIFACT_SCHEMA,
    INGEST_NOTE_SCHEMA,
    INGEST_URL_SCHEMA,
    LINK_KNOWLEDGE_SCHEMA,
    PROMPT_SCHEMA,
    REVIEW_FACT_SCHEMA,
    ROOM_PAGE_SCHEMA,
    RUN_AGENT_SCHEMA,
    STATUS_SCHEMA,
    SYNC_HOME_GRAPH_SCHEMA,
    UNLINK_KNOWLEDGE_SCHEMA,
)


_LOGGER = logging.getLogger(__name__)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the GoodVibes services once per Home Assistant instance."""

    hass.data.setdefault(DOMAIN, {})
    if hass.data[DOMAIN].get("services_registered"):
        return
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

async def async_prompt(call: ServiceCall) -> dict[str, Any]:
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
    payload = _prompt_payload(call.data, message_key="message", body_type="prompt")
    response = await _call_client(runtime.client.prompt(payload))
    runtime.async_apply_submission_response(response)
    return response

async def async_run_agent(call: ServiceCall) -> dict[str, Any]:
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
    payload = _prompt_payload(call.data, message_key=CONF_TASK, body_type="agent")
    payload["task"] = payload.pop("message")
    response = await _call_client(runtime.client.run_agent(payload))
    runtime.async_apply_submission_response(response)
    return response

async def async_status(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime_from_service_call(call.hass, call)
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
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
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
    async_dispatcher_send(runtime.hass, runtime.signal)
    return response

async def async_call_tool(call: ServiceCall) -> dict[str, Any]:
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
    return await _call_client(
        runtime.client.call_tool(call.data[CONF_TOOL], call.data.get(CONF_INPUT, {}))
    )

async def async_home_graph_status(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime_from_service_call(call.hass, call)
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
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
    _ensure_home_graph_enabled(runtime)
    base_payload = runtime.home_graph_base_payload(call.data)
    snapshot = await async_build_home_graph_snapshot(
        runtime.hass,
        runtime.entry,
        base_payload["installationId"],
        base_payload.get("knowledgeSpaceId"),
        include_unexposed=runtime.include_unexposed_entities,
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
        runtime.hass,
        runtime.entry,
        base_payload["installationId"],
        base_payload.get("knowledgeSpaceId"),
        include_unexposed=runtime.include_unexposed_entities,
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
        async_dispatcher_send(runtime.hass, runtime.signal)

async def async_ingest_url(call: ServiceCall) -> dict[str, Any]:
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
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
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
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
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
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
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
    payload = _knowledge_link_payload(runtime, call.data)
    response = await _call_client(runtime.client.home_graph_link(payload))
    runtime.async_apply_home_graph_response(response)
    await async_regenerate_home_graph_pages(runtime, call.data)
    return response

async def async_unlink_knowledge(call: ServiceCall) -> dict[str, Any]:
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
    payload = _knowledge_link_payload(runtime, call.data)
    response = await _call_client(runtime.client.home_graph_unlink(payload))
    runtime.async_apply_home_graph_response(response)
    await async_regenerate_home_graph_pages(runtime, call.data)
    return response

async def async_ask_home_graph(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime_from_service_call(call.hass, call)
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
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
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
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
    payload = runtime.home_graph_base_payload(call.data)
    _copy_optional(call.data, payload, CONF_AREA_ID, "areaId")
    response = await _call_client(runtime.client.home_graph_room_page(payload))
    runtime.async_apply_home_graph_response(response)
    return response

async def async_home_graph_packet(call: ServiceCall) -> dict[str, Any]:
    await _async_verify_admin(call)
    if entity_id := call.data.get(CONF_ENTITY_ID):
        await _async_verify_entity_control(call, [entity_id])
    runtime = _runtime_from_service_call(call.hass, call)
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
    runtime = _runtime_from_service_call(call.hass, call)
    payload = runtime.home_graph_base_payload(call.data)
    for key in (CONF_STATUS, CONF_SEVERITY, CONF_CODE, CONF_LIMIT):
        _copy_optional(call.data, payload, key, key)
    response = await _call_client(runtime.client.home_graph_issues(payload))
    runtime.home_graph_issues = response
    async_dispatcher_send(runtime.hass, runtime.signal)
    return response

async def async_review_fact(call: ServiceCall) -> dict[str, Any]:
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
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
    runtime = _runtime_from_service_call(call.hass, call)
    payload = runtime.home_graph_base_payload(call.data)
    _copy_optional(call.data, payload, CONF_LIMIT, "limit")
    response = await _call_client(runtime.client.home_graph_sources(payload))
    runtime.home_graph_sources = response
    async_dispatcher_send(runtime.hass, runtime.signal)
    return response

async def async_home_graph_pages(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime_from_service_call(call.hass, call)
    payload = runtime.home_graph_base_payload(call.data)
    _copy_optional(call.data, payload, CONF_LIMIT, "limit")
    if "include_markdown" in call.data:
        payload["includeMarkdown"] = call.data["include_markdown"]
    response = await _call_client(runtime.client.home_graph_pages(payload))
    runtime.home_graph_pages = response
    async_dispatcher_send(runtime.hass, runtime.signal)
    return response

async def async_home_graph_browse(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime_from_service_call(call.hass, call)
    payload = runtime.home_graph_base_payload(call.data)
    _copy_optional(call.data, payload, CONF_LIMIT, "limit")
    return await _call_client(runtime.client.home_graph_browse(payload))

async def async_home_graph_map(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime_from_service_call(call.hass, call)
    payload = _map_payload(runtime, call.data)
    return await _call_client(runtime.client.home_graph_map(payload))

async def async_home_graph_export(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime_from_service_call(call.hass, call)
    payload = runtime.home_graph_base_payload(call.data)
    return await _call_client(runtime.client.home_graph_export(payload))

async def async_home_graph_import(call: ServiceCall) -> dict[str, Any]:
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
    payload = {
        **runtime.home_graph_base_payload(call.data),
        "data": call.data["data"],
    }
    response = await _call_client(runtime.client.home_graph_import(payload))
    runtime.async_apply_home_graph_response(response)
    await runtime.async_refresh_home_graph()
    return response

async def async_home_graph_reset(call: ServiceCall) -> dict[str, Any]:
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
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
    await _async_verify_admin(call)
    runtime = _runtime_from_service_call(call.hass, call)
    payload = runtime.home_graph_base_payload(call.data)
    response = await _call_client(runtime.client.home_graph_reindex(payload))
    runtime.async_apply_home_graph_response(response)
    await runtime.async_refresh_home_graph()
    return response

async def _async_verify_admin(call: ServiceCall) -> None:
    """Require an administrator when the call carries a user context.

    Calls with no ``context.user_id`` (automations, scripts, other trusted
    internal callers) are allowed, matching Home Assistant core's handling of
    admin-only services. A call made on behalf of a user is allowed only when
    that user is an administrator; otherwise ``Unauthorized`` is raised.
    """

    user_id = call.context.user_id
    if user_id is None:
        return
    user = await call.hass.auth.async_get_user(user_id)
    if user is None:
        raise UnknownUser(
            context=call.context,
            permission=POLICY_CONTROL,
            user_id=user_id,
        )
    if not user.is_admin:
        raise Unauthorized(
            context=call.context,
            user_id=user_id,
            permission=POLICY_CONTROL,
        )


async def _async_verify_entity_control(
    call: ServiceCall, entity_ids: Iterable[str]
) -> None:
    """Check the calling user's control permission for each targeted entity.

    Applied to handlers that accept an entity id. With no user context the call
    is allowed (trusted internal caller). Administrators pass every entity; a
    non-admin user must hold control permission for each targeted entity.
    """

    user_id = call.context.user_id
    if user_id is None:
        return
    user = await call.hass.auth.async_get_user(user_id)
    if user is None:
        raise UnknownUser(
            context=call.context,
            permission=POLICY_CONTROL,
            user_id=user_id,
        )
    for entity_id in entity_ids:
        if not entity_id:
            continue
        if not user.permissions.check_entity(entity_id, POLICY_CONTROL):
            raise Unauthorized(
                context=call.context,
                user_id=user_id,
                permission=POLICY_CONTROL,
                perm_category="entities",
                entity_id=entity_id,
            )


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

async def _call_client(awaitable) -> dict[str, Any]:
    """Call the daemon client and convert errors for Home Assistant."""

    try:
        return await awaitable
    except GoodVibesClientError as err:
        raise HomeAssistantError(str(err)) from err