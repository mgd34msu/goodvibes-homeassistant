"""GoodVibes daemon client for Home Assistant."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    ENDPOINT_AGENT_TOOLS,
    ENDPOINT_CONVERSATION,
    ENDPOINT_CONVERSATION_CANCEL,
    ENDPOINT_HEALTH,
    ENDPOINT_HOMEASSISTANT_STATUS,
    ENDPOINT_MANIFEST,
    ENDPOINT_STATUS,
    ENDPOINT_TOOLS,
    DEFAULT_CONVERSATION_TIMEOUT_MS,
    TOOL_NAME_TO_ID,
    WEBHOOK_PATH,
)


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
        """Submit a Home Assistant agent-task webhook payload."""

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
        agent_id: str | None = None,
        message_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancel a Home Assistant conversation turn."""

        payload: dict[str, Any] = {}
        if agent_id:
            payload["agentId"] = agent_id
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

    async def session(self, session_id: str) -> dict[str, Any]:
        """Return a shared session record."""

        return await self._request(
            "GET", f"/api/sessions/{quote(session_id, safe='')}"
        )

    async def cancel_session_input(
        self, session_id: str, input_id: str
    ) -> dict[str, Any]:
        """Cancel a queued shared-session input."""

        path = (
            f"/api/sessions/{quote(session_id, safe='')}/inputs/"
            f"{quote(input_id, safe='')}/cancel"
        )
        return await self._request("POST", path, json={})

    async def call_tool(
        self, tool: str, input_payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Invoke a daemon-exposed Home Assistant tool."""

        tool_id = TOOL_NAME_TO_ID.get(tool, tool)
        path = f"/api/channels/tools/homeassistant/{quote(tool_id, safe='')}"
        return await self._request("POST", path, json=dict(input_payload))

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
        headers: Mapping[str, str] | None = None,
        include_daemon_auth: bool = True,
        timeout: int = 20,
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
