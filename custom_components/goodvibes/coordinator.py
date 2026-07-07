"""DataUpdateCoordinator for the GoodVibes integration.

The coordinator is the single owner of the daemon refresh. It replaces the
former hand-rolled ``async_initial_refresh`` fan-out: the actual reads are
batched with ``asyncio.gather`` inside :meth:`GoodVibesRuntimeData.async_refresh`
(four core reads concurrently, plus a concurrent Home Graph pair), and the
coordinator gives that refresh a single owner and deduplicates overlapping
refresh requests.

There is no timer ``update_interval`` on purpose: the integration is
``iot_class: local_push`` and drives its own state from daemon bus events and
explicit service calls, so the coordinator refreshes on demand rather than
polling on a clock.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .data import GoodVibesRuntimeData

_LOGGER = logging.getLogger(__name__)


class GoodVibesDataUpdateCoordinator(DataUpdateCoordinator[None]):
    """Own and deduplicate the batched daemon refresh for one config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        runtime: GoodVibesRuntimeData,
    ) -> None:
        """Initialize the coordinator with no timer-driven polling."""

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            config_entry=entry,
            update_interval=None,
        )
        self.runtime = runtime

    async def _async_update_data(self) -> None:
        """Run the entry's batched daemon refresh."""

        await self.runtime.async_refresh()
        return None
