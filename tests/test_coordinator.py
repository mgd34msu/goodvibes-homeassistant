"""Stage 4: the refresh is batched with asyncio.gather and owned by a coordinator."""

from __future__ import annotations

import asyncio

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.goodvibes.const import DOMAIN
from custom_components.goodvibes.coordinator import GoodVibesDataUpdateCoordinator
from custom_components.goodvibes.data import GoodVibesRuntimeData

DAEMON = "http://127.0.0.1:3421"
ENTRY_DATA = {
    "daemon_url": DAEMON,
    "daemon_token": "tok",
    "webhook_secret": "secret",
    "event_type": "goodvibes_message",
    "home_graph_enabled": True,
    "installation_id": "inst",
    "knowledge_space_id": "",
}


class _ConcurrentClient:
    """Records the peak number of in-flight daemon calls."""

    def __init__(self) -> None:
        self.daemon_url = DAEMON
        self.in_flight = 0
        self.max_in_flight = 0
        self.hg_max_in_flight = 0
        self._counting_hg = False

    async def _tracked(self, result, *, hg: bool = False):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        if hg:
            self.hg_max_in_flight = max(self.hg_max_in_flight, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        return result

    async def health(self):
        return await self._tracked({"ok": True})

    async def status(self):
        return await self._tracked({"status": "running", "version": "1.2.0"})

    async def homeassistant_status(self):
        return await self._tracked({"ok": True})

    async def tool_catalog(self):
        return await self._tracked({"tools": [], "agent_tools": []})

    async def home_graph_status(self, _payload):
        return await self._tracked({"ok": True}, hg=True)

    async def home_graph_issues(self, _payload):
        return await self._tracked({"issues": []}, hg=True)


def _runtime(hass, client) -> GoodVibesRuntimeData:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DAEMON, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    return GoodVibesRuntimeData(
        hass=hass,
        entry=entry,
        client=client,
        event_type="goodvibes_message",
        home_graph_enabled=True,
        installation_id="inst",
        knowledge_space_id=None,
    )


async def test_refresh_runs_core_reads_concurrently(hass):
    """The four core daemon reads overlap instead of running serially."""

    client = _ConcurrentClient()
    runtime = _runtime(hass, client)

    await runtime.async_refresh()

    # health, status, homeassistant_status, tool_catalog were all in flight at once.
    assert client.max_in_flight == 4
    assert runtime.status == "running"


async def test_home_graph_reads_run_concurrently(hass):
    """home_graph status and open-issues reads overlap."""

    client = _ConcurrentClient()
    runtime = _runtime(hass, client)

    await runtime.async_refresh_home_graph()

    assert client.hg_max_in_flight == 2


async def test_coordinator_owns_refresh_and_does_not_poll(hass):
    """The coordinator drives runtime.async_refresh and has no timer interval."""

    client = _ConcurrentClient()
    runtime = _runtime(hass, client)
    coordinator = GoodVibesDataUpdateCoordinator(hass, runtime.entry, runtime)

    assert coordinator.update_interval is None

    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    # Going through the coordinator ran the batched refresh.
    assert client.max_in_flight == 4
