"""Refresh the daemon-registered Home Graph when the home structure changes.

The integration registers the Home Graph snapshot with the daemon once at
startup (see ``__init__._async_auto_sync_home_graph``) and on explicit service
calls. Conversation turns then reference that registered graph on the daemon
side instead of carrying the whole home snapshot in every request, so per-turn
payloads stay small.

To keep that registered graph from going stale, this watcher re-syncs it when
the home's structure changes: an entity, device, or area registry entry is
added, removed, or renamed. Registry updates (not high-frequency state changes)
are the right granularity — the snapshot's structure is what the daemon indexes.
The re-syncs are coalesced through a :class:`~homeassistant.helpers.debounce.Debouncer`
so a burst of registry writes (for example, a newly added integration creating
many entities at once) produces a single refresh after things settle.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.debounce import Debouncer

_LOGGER = logging.getLogger(__name__)

# Coalesce a burst of registry writes into a single Home Graph re-sync. The
# snapshot rebuild and upload are not free, so wait for the home to settle
# before refreshing the daemon's copy.
HOME_GRAPH_RESYNC_COOLDOWN = 30.0


class GoodVibesHomeGraphWatcher:
    """Debounced re-sync of the daemon Home Graph on registry structure changes."""

    def __init__(
        self,
        hass: HomeAssistant,
        resync: Callable[[], Awaitable[Any]],
        *,
        cooldown: float = HOME_GRAPH_RESYNC_COOLDOWN,
    ) -> None:
        """Store the debounced re-sync and its trigger listeners (not yet active)."""

        self._hass = hass
        self._debouncer = Debouncer(
            hass,
            _LOGGER,
            cooldown=cooldown,
            immediate=False,
            function=resync,
        )
        self._unsubscribes: list[Callable[[], None]] = []

    @callback
    def async_start(self) -> None:
        """Subscribe to entity, device, and area registry update events."""

        self._unsubscribes = [
            self._hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, self._async_handle_change
            ),
            self._hass.bus.async_listen(
                dr.EVENT_DEVICE_REGISTRY_UPDATED, self._async_handle_change
            ),
            self._hass.bus.async_listen(
                ar.EVENT_AREA_REGISTRY_UPDATED, self._async_handle_change
            ),
        ]

    async def _async_handle_change(self, _event: Event) -> None:
        """Schedule a coalesced Home Graph re-sync after a registry change."""

        await self._debouncer.async_call()

    @callback
    def async_stop(self) -> None:
        """Unsubscribe from registry events and cancel a pending re-sync."""

        while self._unsubscribes:
            self._unsubscribes.pop()()
        self._debouncer.async_cancel()
