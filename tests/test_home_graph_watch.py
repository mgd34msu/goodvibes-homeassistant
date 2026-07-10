"""Tests for the Home Graph registry-change watcher."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.helpers import (
    area_registry as ar,
    entity_registry as er,
)
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.goodvibes.home_graph_watch import GoodVibesHomeGraphWatcher


async def test_registry_change_triggers_debounced_resync(hass):
    """An entity registry event coalesces into a single Home Graph re-sync."""

    resync = AsyncMock()
    watcher = GoodVibesHomeGraphWatcher(hass, resync, cooldown=1)
    watcher.async_start()

    # Two registry events in quick succession should collapse to one re-sync.
    hass.bus.async_fire(
        er.EVENT_ENTITY_REGISTRY_UPDATED,
        {"action": "create", "entity_id": "light.kitchen"},
    )
    hass.bus.async_fire(
        ar.EVENT_AREA_REGISTRY_UPDATED, {"action": "update", "area_id": "kitchen"}
    )
    await hass.async_block_till_done()

    # The re-sync fires once the debounce cooldown elapses.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done()

    assert resync.await_count == 1

    watcher.async_stop()


async def test_stop_unsubscribes_from_registry_events(hass):
    """After stop, later registry changes no longer trigger a re-sync."""

    resync = AsyncMock()
    watcher = GoodVibesHomeGraphWatcher(hass, resync, cooldown=0)
    watcher.async_start()
    watcher.async_stop()

    hass.bus.async_fire(ar.EVENT_AREA_REGISTRY_UPDATED, {"action": "create"})
    await hass.async_block_till_done()

    assert resync.await_count == 0
