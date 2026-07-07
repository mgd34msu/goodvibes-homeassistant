"""Frontend panel and Home Graph bridge for the GoodVibes integration."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from aiohttp import web
import voluptuous as vol

from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import KEY_HASS, HomeAssistantView, StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .client import GoodVibesClientError, GoodVibesSurfaceMissingError
from .const import (
    CONF_ALLOW_PRIVATE_HOSTS,
    CONF_AREA_ID,
    CONF_CONFIG_ENTRY_ID,
    CONF_DEVICE_ID,
    CONF_ENTITY_ID,
    CONF_INCLUDE_CONFIDENCE,
    CONF_INCLUDE_LINKED_OBJECTS,
    CONF_INCLUDE_SOURCES,
    CONF_LIMIT,
    CONF_MODE,
    CONF_PACKET_TYPE,
    CONF_QUERY,
    CONF_SEVERITY,
    CONF_STATUS,
    CONF_TAGS,
    CONF_TITLE,
    CONF_URL,
    CONF_CODE,
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
    parse_tags as _parse_tags,
    query_payload as _query_payload,
    required_object as _required_object,
    required_text as _required_text,
    review_payload as _review_payload,
    string_list as _string_list,
    truthy as _truthy,
)
from .home_graph import async_build_home_graph_snapshot

_LOGGER = logging.getLogger(__name__)

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
# Home Graph issue triage is now a server-side mode of the daemon's
# `refinement/run` verb (SDK decision record
# 2026-07-07-home-graph-issue-triage.md) — these are just the request
# defaults this integration sends; the daemon owns the actual triage loop,
# confidence gate, and decision cache.
TRIAGE_DEFAULT_LIMIT = 25
TRIAGE_CHUNK_SIZE = 25
TRIAGE_DEFAULT_MIN_CONFIDENCE = 85
TRIAGE_REVIEWER = "homeassistant:auto-triage"
TRIAGE_UNSUPPORTED_REASON = "daemon-triage-not-supported"

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


def _int_value(value: Any, default: int) -> int:
    """Coerce a positive integer with a safe default."""

    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


async def _async_triage_home_graph_issues(
    runtime: Any,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Ask the daemon to triage open Home Graph issues with its own LLM loop.

    This is a thin proxy onto ``POST /home-graph/refinement/run`` with a
    ``triage`` body (SDK decision record
    ``2026-07-07-home-graph-issue-triage.md``): the daemon now owns the triage
    prompt, the confidence gate, and the per-issue decision cache, so there is
    no local classification logic left in this integration. An older daemon
    that does not recognize the ``triage`` input (HTTP 404) or that reports no
    configured triage LLM (``configured: false``) is not papered over with a
    local fallback engine — it is reported honestly as unsupported so the
    panel can say so and the run is skipped.
    """

    base_payload = _base_payload(runtime, data)
    limit = _int_value(_first_value(data, CONF_LIMIT, "limit"), TRIAGE_DEFAULT_LIMIT)
    force = _truthy(_first_value(data, "force", "manual", default=False))
    skip_issue_ids = _string_list(
        _first_value(data, "skipIssueIds", "excludeIssueIds", default=[])
    )
    payload = {
        **base_payload,
        "triage": {
            "minConfidence": TRIAGE_DEFAULT_MIN_CONFIDENCE,
            "limit": limit,
            "chunkSize": TRIAGE_CHUNK_SIZE,
            "force": force,
            "skipIssueIds": skip_issue_ids,
            "reviewer": TRIAGE_REVIEWER,
        },
        "skipGapRefinement": True,
    }

    try:
        response = await runtime.client.home_graph_refinement_run(payload)
    except GoodVibesSurfaceMissingError:
        _LOGGER.info(
            "GoodVibes daemon does not support server-side Home Graph triage "
            "yet; skipping automatic triage this run."
        )
        return _triage_unsupported_result(TRIAGE_UNSUPPORTED_REASON)

    triage = response.get("triage") if isinstance(response, dict) else None
    if not isinstance(triage, dict) or triage.get("configured") is False:
        reason = (
            str(triage.get("reason"))
            if isinstance(triage, dict) and triage.get("reason")
            else TRIAGE_UNSUPPORTED_REASON
        )
        _LOGGER.info(
            "GoodVibes daemon Home Graph triage is not available (%s); "
            "skipping automatic triage this run.",
            reason,
        )
        return _triage_unsupported_result(reason)

    runtime.async_apply_home_graph_response(response)
    await runtime.async_refresh_home_graph()
    return dict(triage)


def _triage_unsupported_result(reason: str) -> dict[str, Any]:
    """Return an honest "server-side triage unavailable" outcome.

    No local re-implementation of the retired Python triage engine — just a
    plain result the panel can present, with every count at zero so it reads
    the same as a batch that found nothing to do.
    """

    return {
        "ok": True,
        "configured": False,
        "reason": reason,
        "processed": 0,
        "skipped": 0,
        "applied": 0,
        "reviewed": 0,
        "decisions": [],
        "remaining": None,
    }


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
