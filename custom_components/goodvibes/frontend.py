"""Frontend panel and Home Graph bridge for the GoodVibes integration."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from aiohttp import web
import voluptuous as vol

from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import KEY_HASS, HomeAssistantView, StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .client import GoodVibesClientError
from .const import (
    CONF_ALLOW_PRIVATE_HOSTS,
    CONF_AREA_ID,
    CONF_ARTIFACT_ID,
    CONF_CONFIG_ENTRY_ID,
    CONF_DEVICE_ID,
    CONF_ENTITY_ID,
    CONF_INCLUDE_CONFIDENCE,
    CONF_INCLUDE_LINKED_OBJECTS,
    CONF_INCLUDE_SOURCES,
    CONF_INSTALLATION_ID,
    CONF_KNOWLEDGE_SPACE_ID,
    CONF_LIMIT,
    CONF_MODE,
    CONF_NODE_ID,
    CONF_PACKET_TYPE,
    CONF_PATH,
    CONF_QUERY,
    CONF_RELATION,
    CONF_SEVERITY,
    CONF_SOURCE_ID,
    CONF_STATUS,
    CONF_TAGS,
    CONF_TARGET_ID,
    CONF_TARGET_KIND,
    CONF_TITLE,
    CONF_URI,
    CONF_URL,
    CONF_CODE,
    DEFAULT_CONVERSATION_TIMEOUT_MS,
    DOMAIN,
    INTEGRATION_VERSION,
    MAX_UPLOAD_BYTES,
)
from .daemon_payloads import (
    artifact_payload as _artifact_payload,
    base_payload as _base_payload,
    camel_key as _camel_key,
    copy_optional_any as _copy_optional_any,
    copy_tags_and_private_hosts as _copy_tags_and_private_hosts,
    ensure_home_graph_enabled as _ensure_home_graph_enabled,
    first_value as _first_value,
    home_graph_payload as _home_graph_payload,
    link_payload as _link_payload,
    map_payload as _map_payload,
    parse_jsonish as _parse_jsonish,
    parse_jsonish_or_text as _parse_jsonish_or_text,
    parse_tags as _parse_tags,
    query_payload as _query_payload,
    required_object as _required_object,
    required_text as _required_text,
    review_payload as _review_payload,
    string_list as _string_list,
    string_set as _string_set,
    target_payload as _target_payload,
    truthy as _truthy,
)
from .home_graph import async_build_home_graph_snapshot

FRONTEND_DIR = Path(__file__).with_name("frontend")
STATIC_URL = "/goodvibes_static"
STATIC_CACHE_HEADERS = False
# The panel asset is cache-busted with the integration version so there is a
# single version knob for the whole integration instead of a second one that
# can drift out of step with const.INTEGRATION_VERSION.
FRONTEND_ASSET_VERSION = INTEGRATION_VERSION
PANEL_COMPONENT = "goodvibes-home-panel"
PANEL_URL_PATH = "goodvibes-home"
PANEL_MODULE_URL = (
    f"{STATIC_URL}/goodvibes-home-panel.js?v={FRONTEND_ASSET_VERSION}"
)
ICON_MODULE_URL = f"{STATIC_URL}/goodvibes-icons.js?v={FRONTEND_ASSET_VERSION}"
PANEL_ICON = "goodvibes:home"
UPLOAD_URL = "/api/goodvibes/home-graph/upload"
UPLOAD_CHUNK_SIZE = 1024 * 1024
WS_HOME_GRAPH_CALL = "goodvibes/home_graph/call"
TRIAGE_CHUNK_SIZE = 25
TRIAGE_CONFIDENCE_THRESHOLD = 0.85
TRIAGE_DEFAULT_LIMIT = 25
TRIAGE_CACHE_VERSION = 1
TRIAGE_CACHE_KEY = f"{DOMAIN}_home_graph_triage"
TRIAGE_CACHE_MAX_ISSUES = 5000

SUPPORTED_ACTIONS = {
    "ask",
    "browse",
    "device_passport",
    "export",
    "ingest_artifact",
    "ingest_note",
    "ingest_url",
    "import",
    "issues",
    "link",
    "map",
    "pages",
    "packet",
    "reindex",
    "refinement_cancel",
    "refinement_run",
    "refinement_task",
    "refinement_tasks",
    "review",
    "room_page",
    "sources",
    "status",
    "sync",
    "triage_issues",
    "unlink",
}


class UploadTooLargeError(HomeAssistantError):
    """Raised when a browser upload exceeds the configured size cap."""


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Register the GoodVibes Home sidebar panel and API bridge."""

    data = hass.data.setdefault(DOMAIN, {})
    if not data.get("frontend_registered"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), STATIC_CACHE_HEADERS)]
        )
        frontend.add_extra_js_url(hass, ICON_MODULE_URL)
        websocket_api.async_register_command(hass, websocket_home_graph_call)
        hass.http.register_view(GoodVibesHomeGraphUploadView())
        data["frontend_registered"] = True

    await async_register_frontend_panel(hass)


async def async_register_frontend_panel(hass: HomeAssistant) -> None:
    """Show the GoodVibes Home panel in the sidebar."""

    data = hass.data.setdefault(DOMAIN, {})
    entry_ids = [
        entry_id
        for entry_id, value in data.items()
        if isinstance(entry_id, str)
        and hasattr(value, "client")
        and hasattr(value, "entry")
    ]
    if data.get("frontend_panel_registered"):
        frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)

    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="GoodVibes Home",
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL_PATH,
        config={
            "_panel_custom": {
                "name": PANEL_COMPONENT,
                "embed_iframe": False,
                "trust_external": False,
                "module_url": PANEL_MODULE_URL,
            },
            "domain": DOMAIN,
            "configEntryId": entry_ids[0] if len(entry_ids) == 1 else None,
            "sidebarIcon": PANEL_ICON,
            "uploadUrl": UPLOAD_URL,
            "wsType": WS_HOME_GRAPH_CALL,
        },
        require_admin=True,
    )
    data["frontend_panel_registered"] = True


@callback
def async_unload_frontend_panel(hass: HomeAssistant) -> None:
    """Remove the GoodVibes Home panel from the sidebar."""

    data = hass.data.setdefault(DOMAIN, {})
    if data.get("frontend_panel_registered"):
        frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
        data["frontend_panel_registered"] = False


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_HOME_GRAPH_CALL,
        vol.Required("action"): vol.In(sorted(SUPPORTED_ACTIONS)),
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
        vol.Optional("payload", default={}): dict,
    }
)
async def websocket_home_graph_call(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle GoodVibes Home panel websocket calls."""

    try:
        runtime = _runtime_from_data(hass, msg)
        payload = dict(msg.get("payload") or {})
        if entry_id := msg.get(CONF_CONFIG_ENTRY_ID):
            payload.setdefault(CONF_CONFIG_ENTRY_ID, entry_id)
        result = await _handle_home_graph_action(hass, runtime, msg["action"], payload)
    except (GoodVibesClientError, HomeAssistantError, ValueError) as err:
        connection.send_error(msg["id"], "goodvibes_error", str(err))
        return
    connection.send_result(msg["id"], result)


class GoodVibesHomeGraphUploadView(HomeAssistantView):
    """Authenticated file upload bridge for daemon Home Graph ingest."""

    url = UPLOAD_URL
    name = "api:goodvibes:home_graph_upload"

    async def post(self, request: web.Request) -> web.Response:
        """Accept a browser upload and proxy it to the GoodVibes daemon."""

        user = request.get("hass_user")
        if user is None or not user.is_admin:
            return self.json({"ok": False, "error": "Admin required"}, status_code=403)

        temp_path: str | None = None
        hass: HomeAssistant = request.app[KEY_HASS]
        try:
            fields, file_info = await _read_multipart_upload(hass, request)
            temp_path = file_info["path"]
            runtime = _runtime_from_data(hass, fields)
            _ensure_home_graph_enabled(runtime)
            payload = _home_graph_payload(runtime, fields)
            _copy_optional_any(fields, payload, (CONF_TITLE, "title"), "title")
            if tags := _parse_tags(fields.get(CONF_TAGS) or fields.get("tags")):
                payload["tags"] = tags
            if CONF_ALLOW_PRIVATE_HOSTS in fields or "allowPrivateHosts" in fields:
                payload["allowPrivateHosts"] = _truthy(
                    _first_value(fields, CONF_ALLOW_PRIVATE_HOSTS, "allowPrivateHosts")
                )
            await _async_sync_home_graph_context(hass, runtime, fields)
            response = await runtime.client.home_graph_upload_artifact(
                payload,
                temp_path,
                filename=file_info["filename"],
                content_type=file_info["content_type"],
            )
            runtime.async_apply_home_graph_response(response)
            await runtime.async_refresh_home_graph()
            return self.json(response)
        except UploadTooLargeError as err:
            return self.json({"ok": False, "error": str(err)}, status_code=413)
        except (GoodVibesClientError, HomeAssistantError, ValueError) as err:
            return self.json({"ok": False, "error": str(err)}, status_code=400)
        finally:
            if temp_path:
                await hass.async_add_executor_job(_remove_file, temp_path)


async def _handle_home_graph_action(
    hass: HomeAssistant,
    runtime: Any,
    action: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Execute a Home Graph action for the frontend panel."""

    _ensure_home_graph_enabled(runtime)
    if action == "status":
        await runtime.async_refresh_home_graph()
        return _status_payload(runtime)
    if action == "sync":
        base_payload = _base_payload(runtime, data)
        snapshot = await async_build_home_graph_snapshot(
            hass,
            runtime.entry,
            base_payload["installationId"],
            base_payload.get("knowledgeSpaceId"),
        )
        response = await runtime.client.home_graph_sync(snapshot)
        runtime.async_apply_home_graph_response(response, sync=True)
        await runtime.async_refresh_home_graph()
        return response
    if action == "sources":
        response = await runtime.client.home_graph_sources(
            _query_payload(runtime, data, {CONF_LIMIT, "limit"})
        )
        runtime.home_graph_sources = response
        async_dispatcher_send(hass, runtime.signal)
        return response
    if action == "pages":
        payload = _query_payload(runtime, data, {CONF_LIMIT, "limit"})
        include_markdown = _first_value(
            data,
            "includeMarkdown",
            "include_markdown",
            default=True,
        )
        payload["includeMarkdown"] = _truthy(include_markdown)
        response = await runtime.client.home_graph_pages(payload)
        runtime.home_graph_pages = response
        async_dispatcher_send(hass, runtime.signal)
        return response
    if action == "issues":
        payload = _query_payload(
            runtime,
            data,
            {
                CONF_STATUS,
                "status",
                CONF_SEVERITY,
                "severity",
                CONF_CODE,
                "code",
                CONF_LIMIT,
                "limit",
            },
        )
        payload.setdefault(CONF_STATUS, "open")
        response = await runtime.client.home_graph_issues(payload)
        runtime.home_graph_issues = response
        async_dispatcher_send(hass, runtime.signal)
        return response
    if action == "browse":
        payload = _query_payload(runtime, data, {"limit"})
        return await runtime.client.home_graph_browse(payload)
    if action == "map":
        return await runtime.client.home_graph_map(_map_payload(runtime, data))
    if action == "export":
        return await runtime.client.home_graph_export(_base_payload(runtime, data))
    if action == "import":
        payload = {
            **_base_payload(runtime, data),
            "data": _required_object(data, "data"),
        }
        response = await runtime.client.home_graph_import(payload)
        runtime.async_apply_home_graph_response(response)
        await runtime.async_refresh_home_graph()
        return response
    if action == "reset":
        dry_run = _truthy(data.get("dryRun") or data.get("dry_run"))
        confirm = str(data.get("confirm") or "").strip()
        if confirm != "RESET" and not dry_run:
            raise HomeAssistantError("Type RESET to reset the Home Graph space.")
        payload = _base_payload(runtime, data)
        if dry_run:
            payload["dryRun"] = True
        response = await runtime.client.home_graph_reset(payload)
        if not dry_run:
            runtime.async_apply_home_graph_response(response)
            await runtime.async_refresh_home_graph()
        return response
    if action == "reindex":
        response = await runtime.client.home_graph_reindex(_base_payload(runtime, data))
        runtime.async_apply_home_graph_response(response)
        await runtime.async_refresh_home_graph()
        return response
    if action == "refinement_tasks":
        payload = _query_payload(
            runtime,
            data,
            {"limit", "state", "subjectId", "gapId"},
        )
        response = await runtime.client.home_graph_refinement_tasks(payload)
        runtime.home_graph_refinement_tasks = response
        async_dispatcher_send(hass, runtime.signal)
        return response
    if action == "refinement_task":
        task_id = _required_text(data, "id", "taskId", "task_id")
        payload = _base_payload(runtime, data)
        response = await runtime.client.home_graph_refinement_task(task_id, payload)
        return response
    if action == "refinement_run":
        payload = _base_payload(runtime, data)
        for source_key, payload_key in (
            ("gapIds", "gapIds"),
            ("gap_ids", "gapIds"),
            ("sourceIds", "sourceIds"),
            ("source_ids", "sourceIds"),
        ):
            if source_key in data:
                values = _string_list(data[source_key])
                if values:
                    payload[payload_key] = values
        if "limit" in data:
            try:
                payload["limit"] = max(1, int(data["limit"]))
            except (TypeError, ValueError):
                payload["limit"] = data["limit"]
        if "force" in data:
            payload["force"] = _truthy(data["force"])
        response = await runtime.client.home_graph_refinement_run(payload)
        runtime.async_apply_home_graph_response(response)
        runtime.home_graph_refinement_tasks = await runtime.client.home_graph_refinement_tasks(
            _query_payload(runtime, {"limit": 100}, {"limit"})
        )
        await runtime.async_refresh_home_graph()
        async_dispatcher_send(hass, runtime.signal)
        return response
    if action == "refinement_cancel":
        task_id = _required_text(data, "id", "taskId", "task_id")
        response = await runtime.client.home_graph_refinement_cancel(
            task_id,
            _base_payload(runtime, data),
        )
        runtime.home_graph_refinement_tasks = await runtime.client.home_graph_refinement_tasks(
            _query_payload(runtime, {"limit": 100}, {"limit"})
        )
        await runtime.async_refresh_home_graph()
        async_dispatcher_send(hass, runtime.signal)
        return response
    if action == "ask":
        if not runtime.home_graph_last_sync_at:
            await _async_sync_home_graph_context(hass, runtime, data)
        payload = {
            **_base_payload(runtime, data),
            "query": _required_text(data, CONF_QUERY, "query"),
            **_query_payload(runtime, data, {CONF_LIMIT, "limit", CONF_MODE, "mode"}),
            "includeSources": _truthy(
                _first_value(data, CONF_INCLUDE_SOURCES, "includeSources", default=True)
            ),
            "includeConfidence": _truthy(
                _first_value(
                    data,
                    CONF_INCLUDE_CONFIDENCE,
                    "includeConfidence",
                    default=False,
                )
            ),
            "includeLinkedObjects": _truthy(
                _first_value(
                    data,
                    CONF_INCLUDE_LINKED_OBJECTS,
                    "includeLinkedObjects",
                    default=True,
                )
            ),
        }
        response = await runtime.client.home_graph_ask(payload)
        runtime.async_apply_home_graph_response(response)
        return response
    if action == "ingest_url":
        await _async_sync_home_graph_context(hass, runtime, data)
        payload = {
            **_home_graph_payload(runtime, data),
            "url": _required_text(data, CONF_URL, "url"),
        }
        _copy_optional_any(data, payload, (CONF_TITLE, "title"), "title")
        _copy_tags_and_private_hosts(data, payload)
        response = await runtime.client.home_graph_ingest_url(payload)
        runtime.async_apply_home_graph_response(response)
        return response
    if action == "ingest_note":
        await _async_sync_home_graph_context(hass, runtime, data)
        payload = {
            **_home_graph_payload(runtime, data),
            "body": _required_text(data, "body", "note"),
        }
        _copy_optional_any(data, payload, (CONF_TITLE, "title"), "title")
        _copy_optional_any(data, payload, ("category",), "category")
        _copy_tags_and_private_hosts(data, payload, private_hosts=False)
        response = await runtime.client.home_graph_ingest_note(payload)
        runtime.async_apply_home_graph_response(response)
        return response
    if action == "ingest_artifact":
        await _async_sync_home_graph_context(hass, runtime, data)
        payload = _artifact_payload(runtime, data)
        response = await runtime.client.home_graph_ingest_artifact(payload)
        runtime.async_apply_home_graph_response(response)
        return response
    if action in {"link", "unlink"}:
        payload = _link_payload(runtime, data)
        call = (
            runtime.client.home_graph_link
            if action == "link"
            else runtime.client.home_graph_unlink
        )
        response = await call(payload)
        runtime.async_apply_home_graph_response(response)
        return response
    if action == "review":
        payload = _review_payload(runtime, data)
        response = await runtime.client.home_graph_review_fact(payload)
        runtime.async_apply_home_graph_response(response)
        await runtime.async_refresh_home_graph()
        return response
    if action == "triage_issues":
        return await _async_triage_home_graph_issues(runtime, data)
    if action == "device_passport":
        payload = _base_payload(runtime, data)
        _copy_optional_any(data, payload, (CONF_DEVICE_ID, "deviceId"), "deviceId")
        response = await runtime.client.home_graph_device_passport(payload)
        runtime.async_apply_home_graph_response(response)
        return response
    if action == "room_page":
        payload = _base_payload(runtime, data)
        _copy_optional_any(data, payload, (CONF_AREA_ID, "areaId"), "areaId")
        _copy_optional_any(data, payload, ("roomId",), "roomId")
        _copy_optional_any(data, payload, (CONF_TITLE, "title"), "title")
        response = await runtime.client.home_graph_room_page(payload)
        runtime.async_apply_home_graph_response(response)
        return response
    if action == "packet":
        payload = {
            **_base_payload(runtime, data),
            "packetKind": _required_text(data, "packetKind", CONF_PACKET_TYPE),
        }
        for key in (
            CONF_AREA_ID,
            CONF_DEVICE_ID,
            CONF_ENTITY_ID,
            CONF_TITLE,
            "roomId",
            "sharingProfile",
        ):
            _copy_optional_any(data, payload, (key,), _camel_key(key))
        if metadata := _parse_jsonish(data.get("metadata")):
            payload["metadata"] = metadata
        response = await runtime.client.home_graph_packet(payload)
        runtime.async_apply_home_graph_response(response)
        return response
    raise HomeAssistantError(f"Unsupported Home Graph action: {action}")


def _status_payload(runtime: Any) -> dict[str, Any]:
    """Return current Home Graph runtime status for the panel."""

    return {
        "status": runtime.home_graph_status,
        "issues": runtime.home_graph_issues,
        "sources": runtime.home_graph_sources,
        "pages": runtime.home_graph_pages,
        "refinementTasks": runtime.home_graph_refinement_tasks,
        "installationId": runtime.installation_id,
        "knowledgeSpaceId": runtime.effective_knowledge_space_id,
        "lastSyncAt": runtime.home_graph_last_sync_at,
        "lastError": runtime.home_graph_last_error,
    }


def _items_from_payload(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    """Extract a list of dict items from common daemon response envelopes."""

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    result = payload.get("result")
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        return _items_from_payload(result, keys)
    return []


def _count_from_payload(payload: Any, keys: tuple[str, ...]) -> int:
    """Extract a count from common daemon response envelopes."""

    if isinstance(payload, dict):
        for key in ("count", "total", "issueCount"):
            value = payload.get(key)
            if value not in (None, ""):
                return _int_value(value, 0)
        status = payload.get("status")
        if isinstance(status, dict):
            for key in ("count", "total", "issueCount"):
                value = status.get(key)
                if value not in (None, ""):
                    return _int_value(value, 0)
        result = payload.get("result")
        if isinstance(result, (dict, list)):
            return _count_from_payload(result, keys)
    return len(_items_from_payload(payload, keys))


def _int_value(value: Any, default: int) -> int:
    """Coerce a positive integer with a safe default."""

    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _float_value(value: Any, default: float) -> float:
    """Coerce a float with a safe default."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _triage_issue_record(
    issue: dict[str, Any],
    node: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a compact issue record for daemon-side LLM review triage."""

    metadata = node.get("metadata") if isinstance(node, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    ha_metadata = metadata.get("homeAssistant")
    if not isinstance(ha_metadata, dict):
        ha_metadata = {}
    record: dict[str, Any] = {
        "issueId": _triage_issue_key(issue),
        "code": issue.get("code"),
        "severity": issue.get("severity"),
        "status": issue.get("status"),
        "message": issue.get("message") or issue.get("title"),
        "nodeId": issue.get("nodeId"),
        "sourceId": issue.get("sourceId"),
    }
    if isinstance(node, dict):
        record["node"] = {
            "id": node.get("id"),
            "kind": node.get("kind"),
            "title": node.get("title") or node.get("name"),
            "summary": node.get("summary"),
            "aliases": (node.get("aliases") or [])[:8],
            "confidence": node.get("confidence"),
            "manufacturer": metadata.get("manufacturer"),
            "model": metadata.get("model"),
            "homeAssistant": {
                "objectKind": ha_metadata.get("objectKind"),
                "objectId": ha_metadata.get("objectId"),
                "entityId": ha_metadata.get("entityId"),
                "deviceId": ha_metadata.get("deviceId"),
                "areaId": ha_metadata.get("areaId"),
                "integrationId": ha_metadata.get("integrationId"),
            },
        }
    return _clean_jsonish(record)


def _triage_issue_key(issue: dict[str, Any]) -> str:
    """Return a stable key the model can echo for a review item."""

    value = (
        issue.get("id")
        or issue.get("issueId")
        or issue.get("nodeId")
        or issue.get("sourceId")
        or issue.get("message")
        or json.dumps(issue, sort_keys=True)
    )
    return str(value)


def _clean_jsonish(value: Any) -> Any:
    """Remove empty values from compact JSON sent to the triage prompt."""

    if isinstance(value, dict):
        return {
            key: cleaned
            for key, item in value.items()
            if (cleaned := _clean_jsonish(item)) not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [
            cleaned
            for item in value
            if (cleaned := _clean_jsonish(item)) not in (None, "", [], {})
        ]
    return value


def _triage_prompt(records: list[dict[str, Any]]) -> str:
    """Build the LLM instruction for automated Home Graph issue triage."""

    payload = json.dumps({"issues": records}, separators=(",", ":"))
    return (
        "You are GoodVibes Home Graph review triage for Home Assistant.\n"
        "Classify issues so people only review uncertain cases.\n"
        "Return only strict JSON with this shape: "
        '{"decisions":[{"issueId":"...","action":"reject|review",'
        '"category":"...","confidence":0.0,"reason":"...",'
        '"fact":{}}]}.\n'
        "Use action reject only when the issue is clearly not applicable or "
        "incorrect and can be safely dismissed. Use action review for anything "
        "uncertain, anything that may require household knowledge, or any "
        "physical device that could plausibly be battery powered.\n"
        "For unknown battery type issues: reject software objects, integrations, "
        "automations, scripts, scenes, areas, helpers, the sun, weather, Home "
        "Assistant host/core/supervisor objects, servers, adapters, hubs, "
        "coordinators, bridges, and mains-powered media devices or appliances. "
        'Include fact {"batteryPowered":false,"batteryType":"none"} for those '
        "not-applicable rejects. "
        "For missing manual issues that are not applicable to software, helpers, "
        'or generated Home Assistant objects, include fact {"manualRequired":false}. '
        "Review sensors, locks, remotes, buttons, keypads, contact sensors, "
        "motion sensors, leak sensors, smoke detectors, thermostats, shades, "
        "blinds, and ambiguous physical devices.\n"
        "Do not invent battery types. Do not choose accept, resolve, edit, or "
        "forget.\n"
        f"Issues JSON:\n{payload}"
    )


def _assistant_text(response: Any) -> str:
    """Extract assistant text from common daemon conversation responses."""

    if not isinstance(response, dict):
        return str(response or "")
    assistant = response.get("assistant")
    if isinstance(assistant, dict):
        return str(
            assistant.get("speechText")
            or assistant.get("text")
            or assistant.get("message")
            or ""
        )
    result = response.get("result")
    if isinstance(result, dict):
        return _assistant_text(result)
    return str(response.get("text") or response.get("message") or result or "")


def _parse_triage_decisions(text: str) -> list[dict[str, Any]]:
    """Parse daemon LLM triage JSON into normalized decision records."""

    payload = _extract_json_payload(text)
    decisions = payload.get("decisions") if isinstance(payload, dict) else payload
    if not isinstance(decisions, list):
        raise HomeAssistantError("Home Graph triage response did not include decisions")

    normalized: list[dict[str, Any]] = []
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        issue_id = str(decision.get("issueId") or decision.get("id") or "").strip()
        if not issue_id:
            continue
        action = str(decision.get("action") or "review").strip().lower()
        if action not in {"reject", "review"}:
            action = "review"
        normalized.append(
            {
                "issueId": issue_id,
                "action": action,
                "category": str(decision.get("category") or "").strip(),
                "confidence": _float_value(decision.get("confidence"), 0.0),
                "reason": str(decision.get("reason") or "").strip(),
                "fact": decision.get("fact")
                if isinstance(decision.get("fact"), dict)
                else None,
            }
        )
    return normalized


def _extract_json_payload(text: str) -> dict[str, Any] | list[Any]:
    """Parse JSON, accepting fenced or lightly wrapped model output."""

    stripped = text.strip()
    if not stripped:
        raise HomeAssistantError("Home Graph triage returned an empty response")
    try:
        parsed = json.loads(stripped)
    except ValueError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise HomeAssistantError("Home Graph triage returned non-JSON output")
        parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, (dict, list)):
        raise HomeAssistantError("Home Graph triage returned a non-object response")
    return parsed


async def _async_load_triage_cache(hass: HomeAssistant) -> dict[str, Any]:
    """Load persisted Home Graph triage fingerprints."""

    store = Store(hass, TRIAGE_CACHE_VERSION, TRIAGE_CACHE_KEY)
    data = await store.async_load()
    if not isinstance(data, dict):
        data = {}
    if not isinstance(data.get("entries"), dict):
        data["entries"] = {}
    return data


async def _async_save_triage_cache(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> None:
    """Persist Home Graph triage fingerprints."""

    _trim_triage_cache(data)
    store = Store(hass, TRIAGE_CACHE_VERSION, TRIAGE_CACHE_KEY)
    await store.async_save(data)


def _triage_entry_cache(data: dict[str, Any], entry_id: str) -> dict[str, Any]:
    """Return mutable triage cache data for a config entry."""

    entries = data.setdefault("entries", {})
    entry = entries.setdefault(str(entry_id), {})
    if not isinstance(entry.get("issues"), dict):
        entry["issues"] = {}
    return entry


def _triage_cache_matches(entry_cache: dict[str, Any], issue: dict[str, Any]) -> bool:
    """Return true if this exact open issue has already been triaged."""

    issues = entry_cache.get("issues")
    if not isinstance(issues, dict):
        return False
    record = issues.get(_triage_issue_key(issue))
    return (
        isinstance(record, dict)
        and record.get("fingerprint") == _triage_issue_fingerprint(issue)
    )


def _remember_triage_decisions(
    entry_cache: dict[str, Any],
    issues: list[dict[str, Any]],
    decisions: dict[str, dict[str, Any]],
) -> None:
    """Remember triage decisions so unchanged manual-review items are not re-run."""

    issue_records = entry_cache.setdefault("issues", {})
    now = dt_util.utcnow().isoformat()
    for issue in issues:
        key = _triage_issue_key(issue)
        decision = decisions.get(key)
        if not decision:
            continue
        issue_records[key] = {
            "fingerprint": _triage_issue_fingerprint(issue),
            "updatedAt": now,
            "decision": _compact_triage_cache_decision(decision),
        }


def _trim_triage_cache(data: dict[str, Any]) -> None:
    """Keep the persisted triage cache bounded."""

    entries = data.get("entries")
    if not isinstance(entries, dict):
        return
    for entry in entries.values():
        if not isinstance(entry, dict) or not isinstance(entry.get("issues"), dict):
            continue
        issues = entry["issues"]
        if len(issues) <= TRIAGE_CACHE_MAX_ISSUES:
            continue
        keep = {
            key
            for key, _record in sorted(
                issues.items(),
                key=lambda item: str(item[1].get("updatedAt", ""))
                if isinstance(item[1], dict)
                else "",
                reverse=True,
            )[:TRIAGE_CACHE_MAX_ISSUES]
        }
        for key in list(issues):
            if key not in keep:
                issues.pop(key, None)


def _triage_issue_fingerprint(issue: dict[str, Any]) -> str:
    """Return a stable fingerprint for the issue state being triaged."""

    value = {
        "key": _triage_issue_key(issue),
        "id": issue.get("id"),
        "issueId": issue.get("issueId"),
        "nodeId": issue.get("nodeId"),
        "sourceId": issue.get("sourceId"),
        "code": issue.get("code"),
        "severity": issue.get("severity"),
        "status": issue.get("status"),
        "title": issue.get("title"),
        "message": issue.get("message"),
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _compact_triage_cache_decision(decision: dict[str, Any]) -> dict[str, Any]:
    """Return only useful scalar triage decision fields for storage."""

    return {
        key: value
        for key, value in {
            "action": decision.get("action"),
            "category": decision.get("category"),
            "confidence": decision.get("confidence"),
            "reason": decision.get("reason"),
        }.items()
        if value not in (None, "")
    }


async def _async_triage_home_graph_issues(
    runtime: Any,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Use the daemon LLM to automatically classify obvious review issues."""

    base_payload = _base_payload(runtime, data)
    limit = _int_value(_first_value(data, CONF_LIMIT, "limit"), TRIAGE_DEFAULT_LIMIT)
    force = _truthy(_first_value(data, "force", "manual", default=False))
    skip_issue_ids = _string_set(
        _parse_jsonish_or_text(
            _first_value(data, "skipIssueIds", "excludeIssueIds", default=[])
        )
    )
    triage_cache = await _async_load_triage_cache(runtime.hass)
    entry_cache = _triage_entry_cache(triage_cache, runtime.entry.entry_id)
    issue_limit = 1000
    issue_payload = await runtime.client.home_graph_issues(
        {**base_payload, "status": "open", "limit": issue_limit}
    )
    browse_payload = await runtime.client.home_graph_browse(
        {**base_payload, "limit": max(250, limit * 3)}
    )
    all_issues = _items_from_payload(issue_payload, ("issues",))
    cached_issue_ids = {
        _triage_issue_key(issue)
        for issue in all_issues
        if not force and _triage_cache_matches(entry_cache, issue)
    }
    issues = [
        issue
        for issue in all_issues
        if _triage_issue_key(issue) not in skip_issue_ids
        and _triage_issue_key(issue) not in cached_issue_ids
    ][:limit]
    nodes = _items_from_payload(browse_payload, ("nodes",))
    node_by_id = {
        str(node.get("id")): node
        for node in nodes
        if isinstance(node, dict) and node.get("id")
    }
    records = [
        _triage_issue_record(issue, node_by_id.get(str(issue.get("nodeId"))))
        for issue in issues
        if isinstance(issue, dict)
    ]
    if not records:
        remaining = _count_from_payload(issue_payload, ("issues",))
        return {
            "ok": True,
            "reviewed": 0,
            "decisions": [],
            "processed": 0,
            "skipped": len(cached_issue_ids),
            "remaining": remaining,
            "reason": (
                "no-untriaged-open-issues"
                if cached_issue_ids
                else "no-open-issues"
            ),
        }

    decisions: list[dict[str, Any]] = []
    for index in range(0, len(records), TRIAGE_CHUNK_SIZE):
        chunk = records[index : index + TRIAGE_CHUNK_SIZE]
        chunk_id = uuid4()
        result = await runtime.client.conversation(
            {
                "message": _triage_prompt(chunk),
                "conversationId": (
                    f"home-graph-triage-{runtime.entry.entry_id}-{chunk_id}"
                ),
                "messageId": f"ha-home-graph-triage-{chunk_id}",
                "displayName": "GoodVibes Home Graph Triage",
                "context": {
                    "source": "home_graph_review_triage",
                    "installationId": base_payload.get("installationId"),
                    "knowledgeSpaceId": base_payload.get("knowledgeSpaceId"),
                },
                "timeoutMs": DEFAULT_CONVERSATION_TIMEOUT_MS,
            },
            timeout_ms=DEFAULT_CONVERSATION_TIMEOUT_MS,
        )
        decisions.extend(_parse_triage_decisions(_assistant_text(result)))

    issue_by_id = {
        _triage_issue_key(issue): issue for issue in issues if isinstance(issue, dict)
    }
    decision_by_id = {
        str(decision.get("issueId") or ""): decision
        for decision in decisions
        if isinstance(decision, dict) and decision.get("issueId")
    }
    applied: list[dict[str, Any]] = []
    for decision in decisions:
        issue_id = str(decision.get("issueId") or "")
        action = str(decision.get("action") or "").strip().lower()
        confidence = _float_value(decision.get("confidence"), 0.0)
        if action != "reject" or confidence < TRIAGE_CONFIDENCE_THRESHOLD:
            continue
        issue = issue_by_id.get(issue_id)
        if not issue:
            continue
        payload = {
            **base_payload,
            "action": "reject",
            "reviewer": "homeassistant:auto-triage",
            "value": _semantic_review_value(issue, decision, confidence),
        }
        if issue.get("id") or issue.get("issueId"):
            payload["issueId"] = str(issue.get("id") or issue.get("issueId"))
        elif issue.get("nodeId"):
            payload["nodeId"] = str(issue["nodeId"])
        elif issue.get("sourceId"):
            payload["sourceId"] = str(issue["sourceId"])
        else:
            continue
        await runtime.client.home_graph_review_fact(payload)
        applied.append(
            {
                "issueId": issue_id,
                "action": "reject",
                "confidence": confidence,
                "reason": payload["value"]["reason"],
            }
        )

    _remember_triage_decisions(entry_cache, issues, decision_by_id)
    await _async_save_triage_cache(runtime.hass, triage_cache)

    await runtime.async_refresh_home_graph()
    remaining = _count_from_payload(runtime.home_graph_issues, ("issues",))
    return {
        "ok": True,
        "processed": len(issues),
        "processedIssueIds": [_triage_issue_key(issue) for issue in issues],
        "skipped": len(cached_issue_ids),
        "reviewed": len(applied),
        "applied": applied,
        "decisions": decisions,
        "remaining": remaining,
    }


def _semantic_review_value(
    issue: dict[str, Any],
    decision: dict[str, Any],
    confidence: float,
) -> dict[str, Any]:
    """Build a semantic review value understood by SDK 0.26.8+."""

    category = str(decision.get("category") or "not_applicable").strip()
    reason = str(
        decision.get("reason") or "LLM classified this issue as not applicable."
    ).strip()
    fact = decision.get("fact") if isinstance(decision.get("fact"), dict) else {}
    fact = dict(fact)
    code = str(issue.get("code") or "")

    if category in {"not_applicable", "false_positive", "not_applicable_or_incorrect"}:
        if code.endswith("unknown_battery"):
            fact.setdefault("batteryPowered", False)
            fact.setdefault("batteryType", "none")
        elif code.endswith("missing_manual"):
            fact.setdefault("manualRequired", False)

    value: dict[str, Any] = {
        "category": category,
        "confidence": confidence,
        "reason": reason,
        "source": "goodvibes_home_graph_triage",
    }
    if fact:
        value["fact"] = fact
    return value


async def _async_sync_home_graph_context(
    hass: HomeAssistant,
    runtime: Any,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send current Home Assistant context before source classification."""

    base_payload = _base_payload(runtime, data or {})
    snapshot = await async_build_home_graph_snapshot(
        hass,
        runtime.entry,
        base_payload["installationId"],
        base_payload.get("knowledgeSpaceId"),
    )
    response = await runtime.client.home_graph_sync(snapshot)
    runtime.async_apply_home_graph_response(response, sync=True)
    return response


def _runtime_from_data(hass: HomeAssistant, data: dict[str, Any]) -> Any:
    """Resolve the GoodVibes runtime selected by a panel or upload request."""

    entries = {
        key: value
        for key, value in hass.data.get(DOMAIN, {}).items()
        if hasattr(value, "client") and hasattr(value, "entry")
    }
    entry_id = data.get(CONF_CONFIG_ENTRY_ID) or data.get("configEntryId")
    if entry_id:
        runtime = entries.get(str(entry_id))
        if runtime is None:
            raise HomeAssistantError(f"Unknown GoodVibes config entry: {entry_id}")
        return runtime
    if len(entries) == 1:
        return next(iter(entries.values()))
    if not entries:
        raise HomeAssistantError("No GoodVibes config entry is loaded")
    raise HomeAssistantError("config_entry_id is required when multiple entries exist")


async def _read_multipart_upload(
    hass: HomeAssistant,
    request: web.Request,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read a multipart browser upload into a temporary file.

    The multipart chunks are read on the event loop (``read_chunk`` is async),
    but every disk operation — creating the temp file, writing each chunk, and
    cleaning up on error — is handed to an executor thread so the loop is never
    blocked on I/O. An oversized upload is refused as soon as it crosses the cap
    instead of being buffered to disk in full first.
    """

    if not request.content_type.startswith("multipart/"):
        raise HomeAssistantError("Upload must use multipart/form-data")

    reader = await request.multipart()
    fields: dict[str, Any] = {}
    file_info: dict[str, Any] | None = None

    while part := await reader.next():
        if part.name == "file":
            if file_info is not None:
                raise HomeAssistantError("Only one file can be uploaded at a time")
            filename = _safe_filename(part.filename)
            content_type = (
                part.headers.get("Content-Type") or "application/octet-stream"
            )
            fd, temp_path = await hass.async_add_executor_job(_create_upload_tempfile)
            size = 0
            try:
                temp_file = await hass.async_add_executor_job(os.fdopen, fd, "wb")
                try:
                    while chunk := await part.read_chunk(UPLOAD_CHUNK_SIZE):
                        size += len(chunk)
                        if size > MAX_UPLOAD_BYTES:
                            raise UploadTooLargeError(_upload_too_large_message())
                        await hass.async_add_executor_job(temp_file.write, chunk)
                finally:
                    await hass.async_add_executor_job(temp_file.close)
            except BaseException:
                await hass.async_add_executor_job(_remove_file, temp_path)
                raise
            file_info = {
                "path": temp_path,
                "filename": filename,
                "content_type": content_type,
                "size": size,
            }
        elif part.name:
            fields[part.name] = await part.text()

    if file_info is None:
        raise HomeAssistantError("Upload requires a file field")
    fields["uploadedAt"] = dt_util.utcnow().isoformat()
    return fields, file_info


def _create_upload_tempfile() -> tuple[int, str]:
    """Create the upload temp file (runs on an executor thread)."""

    return tempfile.mkstemp(prefix="goodvibes-home-graph-")


def _remove_file(path: str) -> None:
    """Delete a temp file, ignoring a missing one (runs on an executor thread)."""

    try:
        os.unlink(path)
    except OSError:
        pass


def _upload_too_large_message() -> str:
    """Return an honest refusal message naming the upload size limit."""

    limit_mib = MAX_UPLOAD_BYTES // (1024 * 1024)
    return f"Upload exceeds the {limit_mib} MiB limit"


def _safe_filename(filename: str | None) -> str:
    """Return a filename safe to forward as multipart metadata."""

    cleaned = Path(filename or "upload").name.strip()
    return cleaned or "upload"
