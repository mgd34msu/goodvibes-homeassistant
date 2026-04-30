"""GoodVibes daemon client for Home Assistant."""

from __future__ import annotations

import json as json_lib
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    ENDPOINT_AGENT_TOOLS,
    ENDPOINT_CONVERSATION,
    ENDPOINT_CONVERSATION_CANCEL,
    ENDPOINT_HEALTH,
    ENDPOINT_HOMEASSISTANT_STATUS,
    ENDPOINT_HOME_GRAPH_ASK,
    ENDPOINT_HOME_GRAPH_BROWSE,
    ENDPOINT_HOME_GRAPH_DEVICE_PASSPORT,
    ENDPOINT_HOME_GRAPH_EXPORT,
    ENDPOINT_HOME_GRAPH_FACT_REVIEW,
    ENDPOINT_HOME_GRAPH_IMPORT,
    ENDPOINT_HOME_GRAPH_INGEST_ARTIFACT,
    ENDPOINT_HOME_GRAPH_INGEST_NOTE,
    ENDPOINT_HOME_GRAPH_INGEST_URL,
    ENDPOINT_HOME_GRAPH_ISSUES,
    ENDPOINT_HOME_GRAPH_LINK,
    ENDPOINT_HOME_GRAPH_MAP,
    ENDPOINT_HOME_GRAPH_PAGES,
    ENDPOINT_HOME_GRAPH_PACKET,
    ENDPOINT_HOME_GRAPH_REINDEX,
    ENDPOINT_HOME_GRAPH_ROOM_PAGE,
    ENDPOINT_HOME_GRAPH_SOURCES,
    ENDPOINT_HOME_GRAPH_STATUS,
    ENDPOINT_HOME_GRAPH_SYNC,
    ENDPOINT_HOME_GRAPH_UNLINK,
    ENDPOINT_MANIFEST,
    ENDPOINT_STATUS,
    ENDPOINT_TOOLS,
    DEFAULT_CONVERSATION_TIMEOUT_MS,
    TOOL_NAME_TO_ID,
    WEBHOOK_PATH,
)

DEFAULT_REQUEST_TIMEOUT = 20
HOME_GRAPH_SYNC_TIMEOUT = 600
HOME_GRAPH_INGEST_TIMEOUT = 3600
HOME_GRAPH_GENERATE_TIMEOUT = 600
HOME_GRAPH_ASK_TIMEOUT = 180


class GoodVibesClientError(Exception):
    """Raised when the GoodVibes daemon returns an error."""


def normalize_daemon_url(value: str) -> str:
    """Normalize a GoodVibes daemon base URL."""

    trimmed = value.strip().rstrip("/")
    if not trimmed:
        raise GoodVibesClientError("GoodVibes daemon URL is required")
    if not trimmed.startswith(("http://", "https://")):
        raise GoodVibesClientError("GoodVibes daemon URL must use http or https")
    return trimmed


class GoodVibesClient:
    """Small async client for the daemon endpoints consumed by this integration."""

    def __init__(
        self,
        hass,
        daemon_url: str,
        daemon_token: str | None,
        webhook_secret: str,
    ) -> None:
        """Initialize the client."""

        self._session = async_get_clientsession(hass)
        self._daemon_url = normalize_daemon_url(daemon_url)
        self._daemon_token = daemon_token.strip() if daemon_token else None
        self._webhook_secret = webhook_secret.strip()

    @property
    def daemon_url(self) -> str:
        """Return the normalized daemon URL."""

        return self._daemon_url

    async def status(self) -> dict[str, Any]:
        """Return the daemon status endpoint."""

        return await self._request("GET", ENDPOINT_STATUS)

    async def health(self) -> dict[str, Any]:
        """Return the daemon Home Assistant health endpoint."""

        return await self._request("GET", ENDPOINT_HEALTH)

    async def manifest(self) -> dict[str, Any]:
        """Return the Home Assistant surface manifest from the daemon."""

        return await self._request("POST", ENDPOINT_MANIFEST, json={})

    async def homeassistant_status(self) -> dict[str, Any]:
        """Return the daemon-side Home Assistant surface status."""

        return await self._request("POST", ENDPOINT_HOMEASSISTANT_STATUS, json={})

    async def tool_catalog(self) -> dict[str, Any]:
        """Return tool and agent-tool catalogs for the Home Assistant surface."""

        tools = await self._request("GET", ENDPOINT_TOOLS)
        agent_tools = await self._request("GET", ENDPOINT_AGENT_TOOLS)
        return {
            "tools": tools.get("tools", []),
            "agent_tools": agent_tools.get("tools", []),
        }

    async def prompt(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Submit a Home Assistant prompt webhook payload."""

        return await self._webhook(payload)

    async def run_agent(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Submit a compatibility run-agent webhook payload."""

        merged = {"type": "agent", **dict(payload)}
        return await self._webhook(merged)

    async def conversation(
        self,
        payload: Mapping[str, Any],
        timeout_ms: int = DEFAULT_CONVERSATION_TIMEOUT_MS,
    ) -> dict[str, Any]:
        """Submit an Assist conversation turn and wait for the final response."""

        request_timeout = max(5, int(timeout_ms / 1000) + 10)
        return await self._request(
            "POST",
            ENDPOINT_CONVERSATION,
            json=dict(payload),
            timeout=request_timeout,
        )

    async def cancel_conversation(
        self,
        *,
        session_id: str | None = None,
        message_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancel a Home Assistant remote-chat conversation."""

        payload: dict[str, Any] = {}
        if session_id:
            payload["sessionId"] = session_id
        if message_id:
            payload["messageId"] = message_id
        return await self._request("POST", ENDPOINT_CONVERSATION_CANCEL, json=payload)

    async def control_command(self, action: str, identifier: str) -> dict[str, Any]:
        """Send a daemon surface control command through the HA webhook."""

        return await self._webhook(
            {
                "type": "control",
                "message": f"{action} {identifier}",
            }
        )

    async def cancel_task(self, task_id: str) -> dict[str, Any]:
        """Cancel a runtime task by task id."""

        path = f"/api/tasks/{quote(task_id, safe='')}/cancel"
        return await self._request("POST", path, json={})

    async def agent_status(self, agent_id: str) -> dict[str, Any]:
        """Return lightweight status for an agent id."""

        return await self._request("GET", f"/task/{quote(agent_id, safe='')}")

    async def runtime_task(self, task_id: str) -> dict[str, Any]:
        """Return a runtime task record."""

        return await self._request("GET", f"/api/tasks/{quote(task_id, safe='')}")

    async def call_tool(
        self, tool: str, input_payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Invoke a daemon-exposed Home Assistant tool."""

        tool_id = TOOL_NAME_TO_ID.get(tool, tool)
        path = f"/api/channels/tools/homeassistant/{quote(tool_id, safe='')}"
        return await self._request("POST", path, json=dict(input_payload))

    async def home_graph_status(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Return daemon Home Graph status."""

        return await self._request(
            "GET", _query_path(ENDPOINT_HOME_GRAPH_STATUS, payload)
        )

    async def home_graph_sync(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Submit a Home Graph snapshot sync."""

        return await self._request(
            "POST",
            ENDPOINT_HOME_GRAPH_SYNC,
            json=dict(payload),
            timeout=HOME_GRAPH_SYNC_TIMEOUT,
        )

    async def home_graph_ingest_url(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Ingest a URL into Home Graph."""

        return await self._request(
            "POST",
            ENDPOINT_HOME_GRAPH_INGEST_URL,
            json=dict(payload),
            timeout=HOME_GRAPH_INGEST_TIMEOUT,
        )

    async def home_graph_ingest_note(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Ingest a note into Home Graph."""

        return await self._request(
            "POST",
            ENDPOINT_HOME_GRAPH_INGEST_NOTE,
            json=dict(payload),
            timeout=HOME_GRAPH_INGEST_TIMEOUT,
        )

    async def home_graph_ingest_artifact(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Ingest an artifact, document, or photo into Home Graph."""

        return await self._request(
            "POST",
            ENDPOINT_HOME_GRAPH_INGEST_ARTIFACT,
            json=dict(payload),
            timeout=HOME_GRAPH_INGEST_TIMEOUT,
        )

    async def home_graph_upload_artifact(
        self,
        payload: Mapping[str, Any],
        file_path: str,
        *,
        filename: str,
        content_type: str | None = None,
        timeout: int = 3600,
    ) -> dict[str, Any]:
        """Upload a local file to Home Graph with multipart/form-data."""

        form = aiohttp.FormData()
        for key, value in payload.items():
            if value in (None, ""):
                continue
            if isinstance(value, (dict, list)):
                form.add_field(
                    key,
                    json_lib.dumps(value, separators=(",", ":")),
                    content_type="application/json",
                )
            else:
                form.add_field(key, str(value))

        with Path(file_path).open("rb") as upload_file:
            form.add_field(
                "file",
                upload_file,
                filename=filename,
                content_type=content_type or "application/octet-stream",
            )
            return await self._request(
                "POST",
                ENDPOINT_HOME_GRAPH_INGEST_ARTIFACT,
                data=form,
                timeout=timeout,
            )

    async def home_graph_link(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Link a Home Graph source or node to a Home Assistant object."""

        return await self._request("POST", ENDPOINT_HOME_GRAPH_LINK, json=dict(payload))

    async def home_graph_unlink(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Unlink a Home Graph source or node from a Home Assistant object."""

        return await self._request(
            "POST", ENDPOINT_HOME_GRAPH_UNLINK, json=dict(payload)
        )

    async def home_graph_ask(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Ask a source-backed Home Graph question."""

        return await self._request(
            "POST",
            ENDPOINT_HOME_GRAPH_ASK,
            json=dict(payload),
            timeout=HOME_GRAPH_ASK_TIMEOUT,
        )

    async def home_graph_device_passport(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Refresh or retrieve a Home Graph device passport."""

        return await self._request(
            "POST",
            ENDPOINT_HOME_GRAPH_DEVICE_PASSPORT,
            json=dict(payload),
            timeout=HOME_GRAPH_GENERATE_TIMEOUT,
        )

    async def home_graph_room_page(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Generate or refresh a Home Graph room page."""

        return await self._request(
            "POST",
            ENDPOINT_HOME_GRAPH_ROOM_PAGE,
            json=dict(payload),
            timeout=HOME_GRAPH_GENERATE_TIMEOUT,
        )

    async def home_graph_packet(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Generate a scoped Home Graph packet."""

        return await self._request(
            "POST",
            ENDPOINT_HOME_GRAPH_PACKET,
            json=dict(payload),
            timeout=HOME_GRAPH_GENERATE_TIMEOUT,
        )

    async def home_graph_issues(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """List Home Graph issues."""

        return await self._request(
            "GET", _query_path(ENDPOINT_HOME_GRAPH_ISSUES, payload)
        )

    async def home_graph_review_fact(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Review a Home Graph fact."""

        return await self._request(
            "POST", ENDPOINT_HOME_GRAPH_FACT_REVIEW, json=dict(payload)
        )

    async def home_graph_sources(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """List Home Graph sources."""

        return await self._request(
            "GET", _query_path(ENDPOINT_HOME_GRAPH_SOURCES, payload)
        )

    async def home_graph_pages(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """List daemon-rendered Home Graph generated pages."""

        return await self._request(
            "GET", _query_path(ENDPOINT_HOME_GRAPH_PAGES, payload)
        )

    async def home_graph_browse(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Browse Home Graph nodes and links."""

        return await self._request(
            "GET", _query_path(ENDPOINT_HOME_GRAPH_BROWSE, payload)
        )

    async def home_graph_map(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Return the daemon-rendered Home Graph visual map."""

        return await self._request(
            "POST", ENDPOINT_HOME_GRAPH_MAP, json=dict(payload)
        )

    async def home_graph_export(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Request a daemon-owned Home Graph export."""

        return await self._request(
            "POST",
            ENDPOINT_HOME_GRAPH_EXPORT,
            json=dict(payload),
            timeout=HOME_GRAPH_GENERATE_TIMEOUT,
        )

    async def home_graph_import(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Request a daemon-owned Home Graph import."""

        return await self._request(
            "POST",
            ENDPOINT_HOME_GRAPH_IMPORT,
            json=dict(payload),
            timeout=HOME_GRAPH_INGEST_TIMEOUT,
        )

    async def home_graph_reindex(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Repair missing or weak Home Graph source extraction."""

        return await self._request(
            "POST",
            ENDPOINT_HOME_GRAPH_REINDEX,
            json=dict(payload),
            timeout=HOME_GRAPH_INGEST_TIMEOUT,
        )

    async def _webhook(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """POST a payload to the daemon Home Assistant webhook."""

        headers = {
            "Accept": "application/json",
            "x-goodvibes-homeassistant-secret": self._webhook_secret,
        }
        return await self._request(
            "POST",
            WEBHOOK_PATH,
            json=dict(payload),
            headers=headers,
            include_daemon_auth=False,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        data: Any = None,
        headers: Mapping[str, str] | None = None,
        include_daemon_auth: bool = True,
        timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ) -> dict[str, Any]:
        """Request JSON from the daemon."""

        request_headers = {"Accept": "application/json"}
        if include_daemon_auth and self._daemon_token:
            request_headers["Authorization"] = f"Bearer {self._daemon_token}"
        if headers:
            request_headers.update(headers)

        try:
            async with self._session.request(
                method,
                f"{self._daemon_url}{path}",
                json=json,
                data=data,
                headers=request_headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                text = await response.text()
                if response.status >= 400:
                    detail = text[:500] if text else response.reason
                    raise GoodVibesClientError(
                        f"GoodVibes HTTP {response.status}: {detail}"
                    )
                if not text.strip():
                    return {}
                try:
                    parsed = await response.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    return {"result": text}
                return parsed if isinstance(parsed, dict) else {"result": parsed}
        except TimeoutError as err:
            raise GoodVibesClientError("GoodVibes daemon request timed out") from err
        except aiohttp.ClientError as err:
            raise GoodVibesClientError(str(err)) from err


def _query_path(path: str, payload: Mapping[str, Any]) -> str:
    """Build a path with non-empty scalar query parameters."""

    query = {
        key: value
        for key, value in payload.items()
        if (
            value not in (None, "", {}, [])
            and isinstance(value, (str, int, float, bool))
        )
    }
    if not query:
        return path
    return f"{path}?{urlencode(query)}"
