"""Frontend panel and Home Graph bridge for the GoodVibes integration."""

from __future__ import annotations

import json
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
    DOMAIN,
)
from .home_graph import async_build_home_graph_snapshot

FRONTEND_DIR = Path(__file__).with_name("frontend")
STATIC_URL = "/goodvibes_static"
STATIC_CACHE_HEADERS = False
FRONTEND_ASSET_VERSION = "0.5.12"
PANEL_COMPONENT = "goodvibes-home-panel"
PANEL_URL_PATH = "goodvibes-home"
PANEL_MODULE_URL = (
    f"{STATIC_URL}/goodvibes-home-panel.js?v={FRONTEND_ASSET_VERSION}"
)
ICON_MODULE_URL = f"{STATIC_URL}/goodvibes-icons.js?v={FRONTEND_ASSET_VERSION}"
PANEL_ICON = "goodvibes:home"
UPLOAD_URL = "/api/goodvibes/home-graph/upload"
WS_HOME_GRAPH_CALL = "goodvibes/home_graph/call"

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
    "packet",
    "review",
    "room_page",
    "sources",
    "status",
    "sync",
    "unlink",
}


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
        try:
            hass: HomeAssistant = request.app[KEY_HASS]
            fields, file_info = await _read_multipart_upload(request)
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
        except (GoodVibesClientError, HomeAssistantError, ValueError) as err:
            return self.json({"ok": False, "error": str(err)}, status_code=400)
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass


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
    if action == "issues":
        response = await runtime.client.home_graph_issues(
            _query_payload(
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
        )
        runtime.home_graph_issues = response
        async_dispatcher_send(hass, runtime.signal)
        return response
    if action == "browse":
        payload = _query_payload(runtime, data, {"limit"})
        return await runtime.client.home_graph_browse(payload)
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
        "installationId": runtime.installation_id,
        "knowledgeSpaceId": runtime.effective_knowledge_space_id,
        "lastSyncAt": runtime.home_graph_last_sync_at,
        "lastError": runtime.home_graph_last_error,
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


def _ensure_home_graph_enabled(runtime: Any) -> None:
    """Raise if Home Graph is disabled."""

    if not runtime.home_graph_enabled:
        raise HomeAssistantError("Home Graph is disabled for this GoodVibes entry")


def _home_graph_payload(runtime: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Build a Home Graph payload from panel data."""

    payload = _base_payload(runtime, data)
    if target := _target_payload(data):
        payload["target"] = target
    if metadata := _parse_jsonish(data.get("metadata")):
        payload["metadata"] = metadata
    return payload


def _base_payload(runtime: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Build a Home Graph base payload from snake_case or camelCase fields."""

    base_data = {
        CONF_INSTALLATION_ID: _first_value(
            data, CONF_INSTALLATION_ID, "installationId"
        ),
        CONF_KNOWLEDGE_SPACE_ID: _first_value(
            data, CONF_KNOWLEDGE_SPACE_ID, "knowledgeSpaceId"
        ),
    }
    return runtime.home_graph_base_payload(base_data)


def _artifact_payload(runtime: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON artifact ingest payload."""

    payload = _home_graph_payload(runtime, data)
    _copy_optional_any(data, payload, (CONF_ARTIFACT_ID, "artifactId"), "artifactId")
    _copy_optional_any(data, payload, (CONF_PATH, "path"), "path")
    _copy_optional_any(data, payload, (CONF_URI, "uri", CONF_URL, "url"), "uri")
    _copy_optional_any(data, payload, (CONF_TITLE, "title"), "title")
    _copy_tags_and_private_hosts(data, payload)
    if not any(key in payload for key in ("artifactId", "path", "uri")):
        raise HomeAssistantError("Artifact ingest requires artifactId, path, or uri")
    return payload


def _link_payload(runtime: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Build a link or unlink payload."""

    payload = _base_payload(runtime, data)
    _copy_optional_any(data, payload, (CONF_SOURCE_ID, "sourceId"), "sourceId")
    _copy_optional_any(data, payload, (CONF_NODE_ID, "nodeId"), "nodeId")
    if "sourceId" not in payload and "nodeId" not in payload:
        raise HomeAssistantError("Linking requires sourceId or nodeId")
    target = _target_payload(data)
    if target is None:
        raise HomeAssistantError("Linking requires a target kind and id")
    payload["target"] = target
    if metadata := _parse_jsonish(data.get("metadata")):
        payload["metadata"] = metadata
    return payload


def _review_payload(runtime: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Build a Home Graph review payload."""

    payload = {
        **_base_payload(runtime, data),
        "action": _required_text(data, "action", "decision"),
    }
    _copy_optional_any(data, payload, ("issueId", "issue_id", "fact_id"), "issueId")
    _copy_optional_any(data, payload, (CONF_NODE_ID, "nodeId"), "nodeId")
    _copy_optional_any(data, payload, (CONF_SOURCE_ID, "sourceId"), "sourceId")
    _copy_optional_any(data, payload, ("reviewer",), "reviewer")
    if (
        "issueId" not in payload
        and "nodeId" not in payload
        and "sourceId" not in payload
    ):
        raise HomeAssistantError("Review requires issueId, nodeId, or sourceId")
    value = _parse_jsonish_or_text(data.get("value"))
    if value is not None:
        payload["value"] = value
    return payload


def _target_payload(data: dict[str, Any]) -> dict[str, Any] | None:
    """Return an optional Home Graph target object."""

    explicit = _parse_jsonish(data.get("target"))
    if isinstance(explicit, dict):
        return explicit
    target_kind = _first_value(data, CONF_TARGET_KIND, "targetKind", "kind")
    target_id = _first_value(data, CONF_TARGET_ID, "targetId", "target_id", "id")
    relation = _first_value(data, CONF_RELATION, "relation")
    title = _first_value(data, CONF_TITLE, "targetTitle", "target_title")
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


def _query_payload(
    runtime: Any,
    data: dict[str, Any],
    allowed: set[str],
) -> dict[str, Any]:
    """Build a query payload with allowed scalar filter fields."""

    payload = _base_payload(runtime, data)
    for key, value in data.items():
        if (
            key in allowed
            and isinstance(value, (str, int, float, bool))
            and value != ""
        ):
            payload[key] = _coerce_query_value(key, value)
    return payload


def _coerce_query_value(
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


async def _read_multipart_upload(
    request: web.Request,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read a multipart browser upload into a temporary file."""

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
            fd, temp_path = tempfile.mkstemp(prefix="goodvibes-home-graph-")
            size = 0
            try:
                with os.fdopen(fd, "wb") as temp_file:
                    while chunk := await part.read_chunk(1024 * 1024):
                        size += len(chunk)
                        temp_file.write(chunk)
            except Exception:
                os.unlink(temp_path)
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


def _safe_filename(filename: str | None) -> str:
    """Return a filename safe to forward as multipart metadata."""

    cleaned = Path(filename or "upload").name.strip()
    return cleaned or "upload"


def _copy_tags_and_private_hosts(
    data: dict[str, Any],
    payload: dict[str, Any],
    *,
    private_hosts: bool = True,
) -> None:
    """Copy common ingest flags."""

    if tags := _parse_tags(_first_value(data, CONF_TAGS, "tags")):
        payload["tags"] = tags
    if private_hosts and (
        CONF_ALLOW_PRIVATE_HOSTS in data or "allowPrivateHosts" in data
    ):
        payload["allowPrivateHosts"] = _truthy(
            _first_value(data, CONF_ALLOW_PRIVATE_HOSTS, "allowPrivateHosts")
        )


def _required_text(data: dict[str, Any], *names: str) -> str:
    """Return a required text field."""

    value = _first_value(data, *names)
    if value in (None, ""):
        raise HomeAssistantError(f"Missing required field: {names[0]}")
    return str(value)


def _required_object(data: dict[str, Any], name: str) -> dict[str, Any]:
    """Return a required object field."""

    value = data.get(name)
    if not isinstance(value, dict):
        raise HomeAssistantError(f"Missing required object field: {name}")
    return value


def _copy_optional_any(
    source: dict[str, Any],
    target: dict[str, Any],
    source_keys: tuple[str, ...],
    target_key: str,
) -> None:
    """Copy the first non-empty source key into a payload."""

    value = _first_value(source, *source_keys)
    if value not in (None, ""):
        target[target_key] = value


def _first_value(
    data: dict[str, Any],
    *names: str,
    default: Any = None,
) -> Any:
    """Return the first non-empty value from a dict."""

    for name in names:
        value = data.get(name)
        if value not in (None, ""):
            return value
    return default


def _parse_jsonish(value: Any) -> Any:
    """Parse JSON fields supplied by forms while accepting native objects."""

    if value in (None, ""):
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return value


def _parse_jsonish_or_text(value: Any) -> Any:
    """Parse JSON when possible, otherwise preserve text values."""

    try:
        return _parse_jsonish(value)
    except ValueError:
        return value


def _parse_tags(value: Any) -> list[str] | None:
    """Parse tags from JSON arrays, lists, or comma-separated strings."""

    if value in (None, ""):
        return None
    parsed = (
        _parse_jsonish(value)
        if isinstance(value, str) and value.strip().startswith("[")
        else value
    )
    if isinstance(parsed, list):
        tags = [str(item).strip() for item in parsed if str(item).strip()]
    else:
        tags = [item.strip() for item in str(parsed).split(",") if item.strip()]
    return tags or None


def _truthy(value: Any) -> bool:
    """Return a form-friendly boolean."""

    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _camel_key(value: str) -> str:
    """Convert a small snake_case key to camelCase."""

    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])
