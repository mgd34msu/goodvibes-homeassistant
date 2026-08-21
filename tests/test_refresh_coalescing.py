"""Tests for GoodVibesRuntimeData.async_refresh() single-flight coalescing.

data.py:488's reconnect watchdog, services.py's ``goodvibes.status`` handler,
and the coordinator can all call ``runtime.async_refresh()`` on the same
runtime. Without coordination, two overlapping calls each read the daemon and
then write the shared dataclass fields, and whichever finishes last wins —
a torn/duplicated refresh a maintainer would not see without forcing the
overlap. These tests force that overlap directly with an ``asyncio.Event``
gate on the fake client, rather than relying on timing.
"""

from __future__ import annotations

import asyncio

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.goodvibes.const import DOMAIN, REQUIRED_DAEMON_CAPABILITIES
from custom_components.goodvibes.data import GoodVibesRuntimeData

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


class _GatedClient:
    """A daemon client double whose ``health()`` blocks until released.

    Lets a test start a refresh, confirm it is mid-flight (health() has been
    entered but not returned), start a second concurrent refresh, and assert
    on whether the second call made its own daemon round-trip or coalesced
    onto the first.
    """

    def __init__(self) -> None:
        self.daemon_url = DAEMON
        self.health_calls = 0
        self.status_calls = 0
        self._gate = asyncio.Event()

    def release(self) -> None:
        self._gate.set()

    async def health(self):
        self.health_calls += 1
        await self._gate.wait()
        return {"ok": True, "capabilities": list(REQUIRED_DAEMON_CAPABILITIES)}

    async def status(self):
        self.status_calls += 1
        return {"status": "running", "version": "1.6.1"}

    async def homeassistant_status(self):
        return {"ok": True}

    async def tool_catalog(self):
        return {"tools": [], "agent_tools": []}

    async def calendar_events_list(self, _payload):
        return {"events": []}


async def _until_entered(client: _GatedClient) -> None:
    """Yield to the event loop until the gated health() call has been entered."""

    for _ in range(100):
        if client.health_calls:
            return
        await asyncio.sleep(0)
    raise AssertionError("health() was never entered")


def _runtime(hass, client: _GatedClient) -> GoodVibesRuntimeData:
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


async def test_concurrent_refresh_coalesces_onto_one_daemon_round_trip(hass):
    """A second caller during an in-flight refresh awaits it instead of redoing it."""

    client = _GatedClient()
    runtime = _runtime(hass, client)

    task1 = asyncio.create_task(runtime.async_refresh())
    await _until_entered(client)
    assert client.health_calls == 1  # the first call is blocked inside health()

    task2 = asyncio.create_task(runtime.async_refresh())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    # The second caller found a refresh already in flight and did not start
    # its own daemon reads.
    assert client.health_calls == 1
    assert client.status_calls == 1

    client.release()
    await task1
    await task2

    assert runtime.daemon_connected is True
    assert runtime.status == "running"
    # Both callers' awaits resolved once the single in-flight refresh finished.
    assert task1.done() and task2.done()


async def test_refresh_task_cleared_after_completion_for_the_next_call(hass):
    """A refresh after the in-flight one finishes triggers a fresh round-trip."""

    client = _GatedClient()
    runtime = _runtime(hass, client)

    client.release()  # do not block the first refresh
    await runtime.async_refresh()
    assert client.health_calls == 1
    assert runtime._refresh_task is None

    await runtime.async_refresh()
    assert client.health_calls == 2  # a genuinely new refresh, not a coalesced one


async def test_three_concurrent_refreshes_all_coalesce(hass):
    """Three overlapping callers still produce exactly one daemon round-trip."""

    client = _GatedClient()
    runtime = _runtime(hass, client)

    tasks = [asyncio.create_task(runtime.async_refresh()) for _ in range(3)]
    await _until_entered(client)
    assert client.health_calls == 1

    client.release()
    await asyncio.gather(*tasks)
    assert client.health_calls == 1
    assert all(task.done() for task in tasks)
