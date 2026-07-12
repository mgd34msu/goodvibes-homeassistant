"""Tests for the daemon-connection watchdog: reconnection and honest availability.

Builds GoodVibesRuntimeData directly with a fake client (the same pattern as
test_coordinator.py) rather than going through full config-entry setup, so
these exercise the reconnect state machine and its effect on entity
availability and repair issues directly.

Covers the three scenarios the reconnect story has to get right: a dropped
connection marks entities unavailable and raises a repair issue; the daemon
returning is detected on its own and resumes normal operation, re-running
whatever the integration hooks in at reconnect; a daemon that answers but
fails the version/capability contract keeps retrying instead of resuming.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.goodvibes.client import GoodVibesUnavailableError
from custom_components.goodvibes.const import (
    DOMAIN,
    ISSUE_DAEMON_CAPABILITIES,
    ISSUE_DAEMON_UNREACHABLE,
    ISSUE_DAEMON_VERSION,
    RECONNECT_INITIAL_DELAY_S,
    REQUIRED_DAEMON_CAPABILITIES,
)
from custom_components.goodvibes.conversation import GoodVibesConversationEntity
from custom_components.goodvibes.data import GoodVibesRuntimeData
from custom_components.goodvibes.sensor import SENSOR_DESCRIPTIONS, GoodVibesSensor

DAEMON = "http://127.0.0.1:3421"
ENTRY_DATA = {
    "daemon_url": DAEMON,
    "daemon_token": "tok",
    "webhook_secret": "secret",
    "event_type": "goodvibes_message",
    "home_graph_enabled": False,
    "installation_id": "inst",
    "knowledge_space_id": "",
}

DAEMON_STATUS_DESCRIPTION = next(
    description
    for description in SENSOR_DESCRIPTIONS
    if description.key == "daemon_status"
)


class _FakeClient:
    """A daemon client double whose reachability and contract are toggleable."""

    def __init__(self) -> None:
        self.daemon_url = DAEMON
        self.reachable = True
        self.version = "1.6.1"
        self.capabilities = list(REQUIRED_DAEMON_CAPABILITIES)

    def _maybe_fail(self) -> None:
        if not self.reachable:
            raise GoodVibesUnavailableError("connection refused")

    async def manifest(self):
        self._maybe_fail()
        return {"device": {"name": "GoodVibes Daemon"}}

    async def health(self):
        self._maybe_fail()
        return {"ok": True, "capabilities": list(self.capabilities)}

    async def status(self):
        self._maybe_fail()
        return {"status": "running", "version": self.version}

    async def homeassistant_status(self):
        self._maybe_fail()
        return {"ok": True}

    async def tool_catalog(self):
        self._maybe_fail()
        return {"tools": [], "agent_tools": []}


def _runtime(hass, client: _FakeClient) -> GoodVibesRuntimeData:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DAEMON, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    return GoodVibesRuntimeData(
        hass=hass,
        entry=entry,
        client=client,
        event_type="goodvibes_message",
        home_graph_enabled=False,
        installation_id="inst",
        knowledge_space_id=None,
    )


def _issue(hass, issue_id: str):
    return ir.async_get(hass).async_get_issue(DOMAIN, issue_id)


async def _advance(hass, seconds: float) -> None:
    """Fire the next scheduled reconnect attempt and let it run to completion."""

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds + 0.5))
    await hass.async_block_till_done()


async def test_drop_marks_entities_unavailable_and_raises_repair_issue(hass):
    """A daemon connection failure marks entities unavailable and raises a repair issue."""

    client = _FakeClient()
    runtime = _runtime(hass, client)
    sensor = GoodVibesSensor(runtime, DAEMON_STATUS_DESCRIPTION)
    conversation = GoodVibesConversationEntity(runtime)

    await runtime.async_refresh()
    assert runtime.daemon_connected is True
    assert sensor.available is True
    assert conversation.available is True
    assert _issue(hass, ISSUE_DAEMON_UNREACHABLE) is None

    client.reachable = False
    await runtime.async_refresh()

    assert runtime.daemon_connected is False
    assert sensor.available is False
    assert conversation.available is False
    assert runtime.status == "unavailable"
    issue = _issue(hass, ISSUE_DAEMON_UNREACHABLE)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.ERROR
    # A reconnect attempt is already scheduled; recovery needs no user action.
    assert runtime.reconnect_unsub is not None


async def test_daemon_returns_reconnects_and_clears_the_repair_issue(hass):
    """The daemon coming back is detected on its own and resumes normal operation."""

    client = _FakeClient()
    runtime = _runtime(hass, client)
    on_reconnected = AsyncMock()
    runtime.on_daemon_reconnected = on_reconnected
    sensor = GoodVibesSensor(runtime, DAEMON_STATUS_DESCRIPTION)
    conversation = GoodVibesConversationEntity(runtime)

    await runtime.async_refresh()
    client.reachable = False
    await runtime.async_refresh()
    assert runtime.daemon_connected is False
    assert _issue(hass, ISSUE_DAEMON_UNREACHABLE) is not None
    on_reconnected.assert_not_awaited()

    client.reachable = True
    await _advance(hass, RECONNECT_INITIAL_DELAY_S)

    assert runtime.daemon_connected is True
    assert sensor.available is True
    assert conversation.available is True
    assert _issue(hass, ISSUE_DAEMON_UNREACHABLE) is None
    # No further attempt is pending once the connection is healthy again.
    assert runtime.reconnect_unsub is None
    # Whatever the integration re-registers with the daemon at initial
    # connect (device registry, Home Graph sync) is re-run on reconnect.
    on_reconnected.assert_awaited_once()


async def test_version_probe_failure_on_reconnect_keeps_retrying(hass):
    """A daemon that answers but fails the version contract keeps retrying honestly."""

    client = _FakeClient()
    runtime = _runtime(hass, client)
    on_reconnected = AsyncMock()
    runtime.on_daemon_reconnected = on_reconnected

    await runtime.async_refresh()
    client.reachable = False
    await runtime.async_refresh()
    assert runtime.daemon_connected is False

    # The daemon comes back, but it is too old to satisfy the version floor.
    client.reachable = True
    client.version = "1.0.0"
    await _advance(hass, RECONNECT_INITIAL_DELAY_S)

    # Reachable, so the generic "unreachable" issue is honestly cleared — but
    # the connection does not resume normal operation, because the
    # version-specific issue already says the real reason.
    assert runtime.daemon_connected is False
    assert _issue(hass, ISSUE_DAEMON_UNREACHABLE) is None
    version_issue = _issue(hass, ISSUE_DAEMON_VERSION)
    assert version_issue is not None
    assert version_issue.translation_placeholders["advertised"] == "1.0.0"
    assert _issue(hass, ISSUE_DAEMON_CAPABILITIES) is None
    on_reconnected.assert_not_awaited()
    # It keeps retrying rather than giving up.
    assert runtime.reconnect_unsub is not None

    # A later attempt with a current version recovers.
    client.version = "1.6.1"
    await _advance(hass, 60)

    assert runtime.daemon_connected is True
    assert _issue(hass, ISSUE_DAEMON_VERSION) is None
    on_reconnected.assert_awaited_once()
