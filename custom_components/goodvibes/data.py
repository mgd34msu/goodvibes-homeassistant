"""Runtime state for the GoodVibes integration.

``GoodVibesRuntimeData`` is the single in-memory state object shared by the
entities and services for one config entry. It also folds inbound daemon bus
events into that state and owns the daemon status/Home Graph refresh. Moved out
of ``__init__.py`` so the package root is setup/orchestration only, and so the
entity platforms can import the type without importing the service handlers.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .client import GoodVibesClient, GoodVibesClientError, GoodVibesUnavailableError
from .const import (
    CONF_INSTALLATION_ID,
    CONF_KNOWLEDGE_SPACE_ID,
    CONF_STATUS,
    DEFAULT_DEVICE_NAME,
    DOMAIN,
    ISSUE_DAEMON_CAPABILITIES,
    ISSUE_DAEMON_UNREACHABLE,
    ISSUE_DAEMON_VERSION,
    MIN_DAEMON_VERSION,
    RECONNECT_INITIAL_DELAY_S,
    RECONNECT_MAX_DELAY_S,
    REQUIRED_DAEMON_CAPABILITIES,
    SIGNAL_UPDATE,
    TERMINAL_STATUSES,
)
from .home_graph import build_home_graph_base_payload, default_knowledge_space_id
from .version_check import DaemonContractCheck, check_daemon_contract

_LOGGER = logging.getLogger(__name__)


def _result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Unwrap daemon channel action envelopes."""

    result = payload.get("result")
    return result if isinstance(result, dict) else payload


def _truncate_state(value: Any, limit: int = 255) -> str | None:
    """Return a Home Assistant state-safe string."""

    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


@dataclass
class GoodVibesRuntimeData:
    """Runtime state shared by GoodVibes entities and services."""

    hass: HomeAssistant
    entry: ConfigEntry
    client: GoodVibesClient
    event_type: str
    home_graph_enabled: bool
    installation_id: str
    knowledge_space_id: str | None
    include_unexposed_entities: bool = False
    manifest: dict[str, Any] = field(default_factory=dict)
    health: dict[str, Any] = field(default_factory=dict)
    daemon_status: dict[str, Any] = field(default_factory=dict)
    homeassistant_status: dict[str, Any] = field(default_factory=dict)
    tool_catalog: dict[str, Any] = field(default_factory=dict)
    home_graph_status: dict[str, Any] = field(default_factory=dict)
    home_graph_issues: dict[str, Any] = field(default_factory=dict)
    home_graph_sources: dict[str, Any] = field(default_factory=dict)
    home_graph_pages: dict[str, Any] = field(default_factory=dict)
    home_graph_refinement_tasks: dict[str, Any] = field(default_factory=dict)
    status: str = "unknown"
    last_reply: str | None = None
    last_payload: dict[str, Any] = field(default_factory=dict)
    last_error: str | None = None
    last_event_at: str | None = None
    home_graph_last_sync_at: str | None = None
    home_graph_last_response: dict[str, Any] = field(default_factory=dict)
    home_graph_last_error: str | None = None
    daemon_contract_ok: bool = True
    daemon_contract_error: str | None = None
    # True only when the daemon is both reachable and satisfies the version and
    # capability contract; entities key their availability off this so a
    # dropped or incompatible connection never serves stale state as if it
    # were current (see async_refresh / _async_mark_daemon_*).
    daemon_connected: bool = True
    daemon_unreachable_error: str | None = None
    # Cancel callback for the pending reconnect attempt (async_call_later),
    # None when no reconnect is scheduled.
    reconnect_unsub: Any | None = None
    reconnect_delay: float = RECONNECT_INITIAL_DELAY_S
    # Set by async_setup_entry to redo the daemon-side setup work (device
    # registry refresh, Home Graph sync) once a reconnect succeeds, so
    # recovering is equivalent to a fresh setup with no user action.
    on_daemon_reconnected: Callable[[], Awaitable[None]] | None = None
    active_session_id: str | None = None
    active_message_id: str | None = None
    active_agent_id: str | None = None
    active_run_id: str | None = None
    unsubscribe_event: Any | None = None
    unsubscribe_auto_sync: Any | None = None
    # The registry-change watcher that keeps the daemon Home Graph fresh.
    home_graph_watcher: Any | None = None
    # The perception-trigger manager (state-change -> attributed session).
    perception_manager: Any | None = None
    # The causal-provenance tracker (context chain -> cause of a state change).
    provenance_tracker: Any | None = None
    # The consent-gated habit miner and its latest proposals (opt-in; may be None).
    habit_miner: Any | None = None
    habit_proposals: list[dict[str, Any]] = field(default_factory=list)
    # The DataUpdateCoordinator that owns the batched refresh for this entry.
    # Set in async_setup_entry after both objects exist.
    coordinator: Any = None

    @property
    def signal(self) -> str:
        """Return this entry's dispatcher signal."""

        return f"{SIGNAL_UPDATE}_{self.entry.entry_id}"

    @property
    def provenance_resolver(self):
        """Return the causal-provenance resolver, or ``None`` when unavailable.

        Handed to the Home Graph snapshot builder so each entity's state carries
        the cause attributed from its Home Assistant context chain.
        """

        tracker = self.provenance_tracker
        return tracker.resolve if tracker is not None else None

    @property
    def effective_knowledge_space_id(self) -> str:
        """Return the Home Graph knowledge space id."""

        return self.knowledge_space_id or default_knowledge_space_id(
            self.installation_id
        )

    def home_graph_base_payload(
        self, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return common Home Graph payload fields for this config entry."""

        data = data or {}
        installation_id = str(data.get(CONF_INSTALLATION_ID) or self.installation_id)
        knowledge_space_id = str(
            data.get(CONF_KNOWLEDGE_SPACE_ID) or self.effective_knowledge_space_id
        )
        return build_home_graph_base_payload(installation_id, knowledge_space_id)

    @property
    def device_identifier(self) -> str:
        """Return the registry identifier for the daemon device."""

        device = self.manifest.get("device", {})
        identifiers = device.get("identifiers")
        if isinstance(identifiers, list) and identifiers:
            return str(identifiers[0])
        return self.entry.unique_id or self.client.daemon_url

    @property
    def device_name(self) -> str:
        """Return the daemon device name."""

        device = self.manifest.get("device", {})
        return str(device.get("name") or DEFAULT_DEVICE_NAME)

    @property
    def device_model(self) -> str:
        """Return the daemon device model."""

        device = self.manifest.get("device", {})
        return str(device.get("model") or DEFAULT_DEVICE_NAME)

    @property
    def sw_version(self) -> str | None:
        """Return the daemon software version."""

        device = self.manifest.get("device", {})
        value = device.get("swVersion") or self.daemon_status.get("version")
        return str(value) if value else None

    async def async_fetch_manifest(self) -> None:
        """Fetch the daemon Home Assistant surface manifest for device info."""

        try:
            raw_manifest = await self.client.manifest()
            self.manifest = _result_payload(raw_manifest)
        except GoodVibesClientError as err:
            self.last_error = str(err)

    async def async_initial_refresh(self) -> None:
        """Refresh daemon state without failing integration setup."""

        await self.async_fetch_manifest()
        await self.async_refresh()

    async def async_refresh(self) -> None:
        """Refresh daemon status and tool catalog.

        The four core daemon reads (health, status, HA-surface status, tool
        catalog) are independent, so they are dispatched concurrently with
        asyncio.gather instead of one serial round-trip after another. The Home
        Graph reads run as a second concurrent batch inside
        async_refresh_home_graph.

        This is also the daemon-connection probe: a connection failure here
        (as opposed to an error response from a reachable daemon) marks the
        connection down, raises the honest repair issue, and starts the
        reconnect watchdog. This method never raises a client error itself —
        callers (setup, the coordinator, the reconnect watchdog) can always
        await it and read the outcome off ``daemon_connected``/``status``.
        """

        try:
            health, daemon_status, raw_surface_status, tool_catalog = (
                await asyncio.gather(
                    self.client.health(),
                    self.client.status(),
                    self.client.homeassistant_status(),
                    self.client.tool_catalog(),
                )
            )
        except GoodVibesUnavailableError as err:
            self._async_mark_daemon_unreachable(str(err))
            async_dispatcher_send(self.hass, self.signal)
            return
        except GoodVibesClientError as err:
            self.status = "error"
            self.last_error = str(err)
            await self.async_refresh_home_graph()
            async_dispatcher_send(self.hass, self.signal)
            return

        self.health = health
        self.daemon_status = daemon_status
        self.status = str(daemon_status.get("status") or "running")
        self.homeassistant_status = _result_payload(raw_surface_status)
        if self.homeassistant_status.get("ok") is False:
            self.status = "homeassistant_error"
            self.last_error = str(
                self.homeassistant_status.get("error") or "Home Assistant surface error"
            )
        self.tool_catalog = tool_catalog
        if self.status != "homeassistant_error":
            self.last_error = None
        check = self._async_check_daemon_contract(daemon_status, health)
        if check.ok:
            self._async_mark_daemon_reachable()
        else:
            # The daemon answered but fails the version/capability contract.
            # daemon_version_unsupported / daemon_capabilities_missing (raised
            # above by _async_check_daemon_contract) already say honestly why;
            # this just keeps entities unavailable and retries instead of
            # resuming normal operation against an incompatible daemon.
            self._async_mark_daemon_not_ready()
        await self.async_refresh_home_graph()
        async_dispatcher_send(self.hass, self.signal)

    def _async_check_daemon_contract(
        self,
        daemon_status: dict[str, Any],
        health: dict[str, Any],
    ) -> DaemonContractCheck:
        """Compare the daemon's advertised contract to the one this client speaks.

        Reads the daemon software version (``/status``) and the Home Assistant
        surface capabilities (``/api/homeassistant/health``) and raises a Home
        Assistant repair issue when the daemon is older than the minimum this
        client needs, or when a surface capability it relies on is missing.
        Clears the issues again once the daemon satisfies the contract. Returns
        the check so the caller can gate resuming normal operation on it (see
        async_refresh).
        """

        check: DaemonContractCheck = check_daemon_contract(
            daemon_status,
            health,
            minimum_version=MIN_DAEMON_VERSION,
            required_capabilities=REQUIRED_DAEMON_CAPABILITIES,
        )
        self.daemon_contract_ok = check.ok
        if check.version_ok:
            _async_clear_repair_issue(self.hass, ISSUE_DAEMON_VERSION)
        else:
            _async_create_repair_issue(
                self.hass,
                ISSUE_DAEMON_VERSION,
                ISSUE_DAEMON_VERSION,
                {
                    "advertised": str(check.advertised_version or "unknown"),
                    "minimum": check.minimum_version,
                },
                severity=ir.IssueSeverity.ERROR,
            )
        if check.capabilities_ok:
            _async_clear_repair_issue(self.hass, ISSUE_DAEMON_CAPABILITIES)
        else:
            _async_create_repair_issue(
                self.hass,
                ISSUE_DAEMON_CAPABILITIES,
                ISSUE_DAEMON_CAPABILITIES,
                {"capabilities": ", ".join(check.missing_capabilities)},
                severity=ir.IssueSeverity.ERROR,
            )
        if check.ok:
            self.daemon_contract_error = None
        else:
            problems: list[str] = []
            if not check.version_ok:
                problems.append(
                    f"daemon {check.advertised_version or 'unknown'} is older than "
                    f"the required {check.minimum_version}"
                )
            if not check.capabilities_ok:
                problems.append(
                    "missing surface capabilities: "
                    + ", ".join(check.missing_capabilities)
                )
            self.daemon_contract_error = "; ".join(problems)
        return check

    @callback
    def _async_mark_daemon_reachable(self) -> None:
        """Record a fully healthy daemon connection and stop retrying.

        Reachable and contract-compatible: entities resume normal operation
        and the daemon_unreachable repair issue clears. (daemon_version /
        daemon_capabilities are handled separately by
        _async_check_daemon_contract, since they can be raised or cleared
        independently of reachability.)
        """

        if not self.daemon_connected:
            _LOGGER.info("GoodVibes daemon connection restored")
        self.daemon_connected = True
        self.daemon_unreachable_error = None
        self.reconnect_delay = RECONNECT_INITIAL_DELAY_S
        _async_clear_repair_issue(self.hass, ISSUE_DAEMON_UNREACHABLE)

    @callback
    def _async_mark_daemon_not_ready(self) -> None:
        """The daemon answered but fails the version/capability contract.

        Distinct from an unreachable daemon: the connection itself is fine, so
        this does not raise ISSUE_DAEMON_UNREACHABLE (that would be
        dishonest) — the version/capability issues already say why. Entities
        still report unavailable and the reconnect watchdog keeps retrying,
        because this client cannot safely operate against an incompatible
        daemon.
        """

        self.daemon_connected = False
        self.daemon_unreachable_error = None
        _async_clear_repair_issue(self.hass, ISSUE_DAEMON_UNREACHABLE)
        self._async_ensure_reconnect_scheduled()

    @callback
    def _async_mark_daemon_unreachable(self, error: str) -> None:
        """Record that the daemon connection dropped.

        Entities key their availability off ``daemon_connected`` so they
        report unavailable instead of serving stale state, and a repair issue
        tells the user honestly what happened. Schedules the reconnect
        watchdog (if one is not already pending) so recovery needs no user
        action.
        """

        was_connected = self.daemon_connected
        self.daemon_connected = False
        self.daemon_unreachable_error = error
        self.status = "unavailable"
        self.last_error = error
        _async_create_repair_issue(
            self.hass,
            ISSUE_DAEMON_UNREACHABLE,
            ISSUE_DAEMON_UNREACHABLE,
            {"error": error[:200]},
            severity=ir.IssueSeverity.ERROR,
        )
        if was_connected:
            _LOGGER.warning("GoodVibes daemon connection lost: %s", error)
        self._async_ensure_reconnect_scheduled()

    @callback
    def _async_ensure_reconnect_scheduled(self) -> None:
        """Schedule the next reconnect attempt if one is not already pending.

        Uses the current backoff delay, then doubles it (capped at
        RECONNECT_MAX_DELAY_S) so a second consecutive failure waits longer
        than the first. _async_mark_daemon_reachable resets the delay back to
        RECONNECT_INITIAL_DELAY_S once a probe succeeds, so the next drop
        starts the ramp over.
        """

        if self.reconnect_unsub is not None:
            return
        delay = self.reconnect_delay
        self.reconnect_unsub = async_call_later(
            self.hass, delay, self._async_reconnect_attempt
        )
        self.reconnect_delay = min(delay * 2, RECONNECT_MAX_DELAY_S)

    async def _async_reconnect_attempt(self, _now: Any) -> None:
        """One reconnect probe.

        Repeats the same daemon reads setup makes (manifest fetch, then the
        batched core refresh with its version/capability probe). A failure
        here runs straight back through async_refresh's own
        _async_mark_daemon_unreachable/_async_mark_daemon_not_ready, which
        schedules the next attempt at the (already-doubled) backoff delay —
        this method does not need to schedule retries itself. On success it
        runs ``on_daemon_reconnected`` (set by async_setup_entry) to redo the
        rest of what setup does against the daemon — currently the device
        registry refresh and the Home Graph sync — so reconnecting is
        equivalent to a fresh setup and needs no action from the user.
        """

        self.reconnect_unsub = None
        await self.async_fetch_manifest()
        await self.async_refresh()
        if self.daemon_connected and self.on_daemon_reconnected is not None:
            await self.on_daemon_reconnected()

    async def async_refresh_home_graph(self) -> None:
        """Refresh daemon Home Graph status without failing core status."""

        if not self.home_graph_enabled:
            self.home_graph_status = {"enabled": False, "status": "disabled"}
            self.home_graph_issues = {}
            self.home_graph_last_error = None
            _async_clear_home_graph_issue(self.hass, "home_graph_unavailable")
            _async_clear_home_graph_issue(self.hass, "home_graph_issues")
            return
        try:
            base_payload = self.home_graph_base_payload()
            # Status and open-issues are independent reads; fetch concurrently.
            self.home_graph_status, self.home_graph_issues = await asyncio.gather(
                self.client.home_graph_status(base_payload),
                self.client.home_graph_issues({**base_payload, CONF_STATUS: "open"}),
            )
            self.home_graph_last_error = None
            _async_clear_home_graph_issue(self.hass, "home_graph_unavailable")
            issue_count = _home_graph_issue_count(self.home_graph_issues)
            if issue_count > 0:
                _async_create_home_graph_issue(
                    self.hass,
                    "home_graph_issues",
                    "home_graph_issues",
                    {"count": str(issue_count)},
                )
            else:
                _async_clear_home_graph_issue(self.hass, "home_graph_issues")
        except GoodVibesClientError as err:
            self.home_graph_status = {"ok": False, "status": "error"}
            self.home_graph_last_error = str(err)
            _async_clear_home_graph_issue(self.hass, "home_graph_issues")
            _async_create_home_graph_issue(
                self.hass,
                "home_graph_unavailable",
                "home_graph_unavailable",
                {"error": str(err)[:200]},
            )

    @callback
    def async_handle_event(self, event) -> None:
        """Handle an outbound GoodVibes Home Assistant bus event."""

        payload = dict(event.data)
        self.last_payload = payload
        self.last_event_at = dt_util.utcnow().isoformat()

        event_status = payload.get("status") or payload.get("type") or "message"
        self.status = _truncate_state(event_status) or "message"

        body = payload.get("body") or payload.get("message") or payload.get("text")
        title = payload.get("title")
        if body:
            self.last_reply = str(body)
        elif title:
            self.last_reply = str(title)

        session_id = payload.get("sessionId") or payload.get("session_id")
        message_id = payload.get("messageId") or payload.get("message_id")
        agent_id = payload.get("agentId") or payload.get("agent_id")
        run_id = payload.get("runId") or payload.get("run_id") or payload.get("jobId")

        status_lower = str(event_status).lower()
        if status_lower in TERMINAL_STATUSES:
            if message_id is None or str(message_id) == self.active_message_id:
                self.active_message_id = None
            if agent_id is None or str(agent_id) == self.active_agent_id:
                self.active_agent_id = None
            if session_id is None or str(session_id) == self.active_session_id:
                self.active_session_id = None
            if run_id is None or str(run_id) == self.active_run_id:
                self.active_run_id = None
        else:
            if session_id:
                self.active_session_id = str(session_id)
            if message_id:
                self.active_message_id = str(message_id)
            if agent_id:
                self.active_agent_id = str(agent_id)
            if run_id:
                self.active_run_id = str(run_id)

        if status_lower in {"error", "failed"}:
            self.last_error = str(body or title or "GoodVibes reported an error")

        async_dispatcher_send(self.hass, self.signal)

    @callback
    def async_apply_submission_response(self, response: dict[str, Any]) -> None:
        """Update active ids from a daemon submission response."""

        if session_id := response.get("sessionId"):
            self.active_session_id = str(session_id)
        if message_id := response.get("messageId"):
            self.active_message_id = str(message_id)
        if agent_id := response.get("agentId"):
            self.active_agent_id = str(agent_id)
        self.status = "queued" if response.get("queued") else "acknowledged"
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def async_start_conversation_turn(self, message_id: str) -> None:
        """Mark a synchronous remote-chat conversation turn as in progress."""

        self.active_message_id = message_id
        self.status = "processing"
        self.last_error = None
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def async_apply_conversation_response(self, response: dict[str, Any]) -> None:
        """Update runtime state from a synchronous conversation response."""

        response_status = (
            response.get("status") or response.get("mode") or "conversation"
        )
        if session_id := response.get("sessionId"):
            self.active_session_id = str(session_id)
        if message_id := response.get("messageId"):
            if str(message_id) == self.active_message_id:
                self.active_message_id = None
        elif str(response_status).lower() in TERMINAL_STATUSES:
            self.active_message_id = None
        if agent_id := response.get("agentId"):
            self.active_agent_id = str(agent_id)
        assistant = response.get("assistant")
        if isinstance(assistant, dict):
            reply = assistant.get("speechText") or assistant.get("text")
            if reply:
                self.last_reply = str(reply)
        self.status = str(response_status)
        if response.get("ok") is False:
            self.last_error = str(
                response.get("error") or "GoodVibes conversation failed"
            )
        else:
            self.last_error = None
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def async_apply_conversation_error(self, message_id: str, error: str) -> None:
        """Update runtime state when a synchronous conversation request fails."""

        if self.active_message_id == message_id:
            self.active_message_id = None
        self.status = "error"
        self.last_error = error
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def async_apply_home_graph_response(
        self,
        response: dict[str, Any],
        *,
        sync: bool = False,
    ) -> None:
        """Update runtime state from a Home Graph response."""

        self.home_graph_last_response = response
        if sync:
            self.home_graph_last_sync_at = dt_util.utcnow().isoformat()
        if response.get("ok") is False:
            self.home_graph_last_error = str(
                response.get("error") or "Home Graph request failed"
            )
        else:
            self.home_graph_last_error = None
        if status := response.get("status"):
            self.home_graph_status = {
                **self.home_graph_status,
                "status": status,
            }
        async_dispatcher_send(self.hass, self.signal)


def _async_create_repair_issue(
    hass: HomeAssistant,
    issue_id: str,
    translation_key: str,
    placeholders: dict[str, str] | None = None,
    *,
    severity: ir.IssueSeverity = ir.IssueSeverity.WARNING,
) -> None:
    """Create a Home Assistant repair issue for the GoodVibes integration."""

    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=severity,
        translation_key=translation_key,
        translation_placeholders=placeholders,
    )


def _async_clear_repair_issue(hass: HomeAssistant, issue_id: str) -> None:
    """Clear a GoodVibes Home Assistant repair issue."""

    ir.async_delete_issue(hass, DOMAIN, issue_id)


def _async_create_home_graph_issue(
    hass: HomeAssistant,
    issue_id: str,
    translation_key: str,
    placeholders: dict[str, str] | None = None,
) -> None:
    """Create a Home Assistant repair issue for Home Graph."""

    _async_create_repair_issue(hass, issue_id, translation_key, placeholders)


def _async_clear_home_graph_issue(hass: HomeAssistant, issue_id: str) -> None:
    """Clear a Home Assistant repair issue for Home Graph."""

    _async_clear_repair_issue(hass, issue_id)


def _home_graph_issue_count(payload: dict[str, Any]) -> int:
    """Return the number of daemon-reported Home Graph issues."""

    issues = payload.get("issues")
    if isinstance(issues, list):
        return len(issues)
    count = payload.get("count")
    return count if isinstance(count, int) else 0
