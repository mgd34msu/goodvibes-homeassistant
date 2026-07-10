"""Home Assistant integration for GoodVibes.

The package root is setup/orchestration only. Runtime state lives in
``data.py`` (:class:`GoodVibesRuntimeData`), service handlers in ``services.py``,
service schemas in ``schemas.py``, the shared daemon payload builders in
``daemon_payloads.py``, and the sidebar panel/upload proxy in ``frontend.py``.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .client import GoodVibesClient, GoodVibesClientError
from .const import (
    CONF_DAEMON_TOKEN,
    CONF_DAEMON_URL,
    CONF_EVENT_TYPE,
    CONF_HOME_GRAPH_ENABLED,
    CONF_INCLUDE_UNEXPOSED_ENTITIES,
    CONF_INSTALLATION_ID,
    CONF_KNOWLEDGE_SPACE_ID,
    CONF_WEBHOOK_SECRET,
    DEFAULT_EVENT_TYPE,
    DEFAULT_HOME_GRAPH_ENABLED,
    DEFAULT_INCLUDE_UNEXPOSED_ENTITIES,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import GoodVibesDataUpdateCoordinator
from .data import GoodVibesRuntimeData
from .home_graph import async_build_home_graph_snapshot, derive_installation_id
from .services import async_setup_services
from .frontend import async_setup_frontend, async_unload_frontend_panel

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Re-exported so the entity platforms (sensor/conversation/update) and the tests
# can keep importing the runtime type from the package root.
__all__ = ["GoodVibesRuntimeData"]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up GoodVibes services."""

    await async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GoodVibes from a config entry."""

    client = GoodVibesClient(
        hass,
        entry.data[CONF_DAEMON_URL],
        entry.data.get(CONF_DAEMON_TOKEN),
        entry.data[CONF_WEBHOOK_SECRET],
    )
    runtime = GoodVibesRuntimeData(
        hass=hass,
        entry=entry,
        client=client,
        event_type=entry.data.get(CONF_EVENT_TYPE, DEFAULT_EVENT_TYPE),
        home_graph_enabled=entry.data.get(
            CONF_HOME_GRAPH_ENABLED, DEFAULT_HOME_GRAPH_ENABLED
        ),
        installation_id=entry.data.get(CONF_INSTALLATION_ID)
        or derive_installation_id(hass, entry),
        knowledge_space_id=entry.data.get(CONF_KNOWLEDGE_SPACE_ID) or None,
        include_unexposed_entities=entry.data.get(
            CONF_INCLUDE_UNEXPOSED_ENTITIES, DEFAULT_INCLUDE_UNEXPOSED_ENTITIES
        ),
    )

    coordinator = GoodVibesDataUpdateCoordinator(hass, entry, runtime)
    runtime.coordinator = coordinator

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = runtime

    await async_setup_frontend(hass)
    # Device info comes from the manifest; fetch it, then let the coordinator own
    # the first batched daemon refresh. The refresh never raises (it records the
    # error into runtime state), so a briefly unreachable daemon does not block
    # setup.
    await runtime.async_fetch_manifest()
    await coordinator.async_config_entry_first_refresh()
    runtime.unsubscribe_event = hass.bus.async_listen(
        runtime.event_type, runtime.async_handle_event
    )

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, runtime.device_identifier)},
        manufacturer="GoodVibes",
        model=runtime.device_model,
        name=runtime.device_name,
        sw_version=runtime.sw_version,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if runtime.home_graph_enabled:
        # Scope the auto-sync task to the config entry so Home Assistant cancels
        # it when the entry is unloaded or reloaded; a bare hass.create_task
        # would leak a running sync past the entry's lifetime.
        task_name = f"{DOMAIN}_auto_sync_{entry.entry_id}"
        if getattr(hass, "is_running", False):
            entry.async_create_background_task(
                hass, _async_auto_sync_home_graph(runtime), name=task_name
            )
        else:
            runtime.unsubscribe_auto_sync = hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED,
                lambda _event: entry.async_create_background_task(
                    hass, _async_auto_sync_home_graph(runtime), name=task_name
                ),
            )
    return True


async def _async_auto_sync_home_graph(runtime: GoodVibesRuntimeData) -> None:
    """Refresh the daemon Home Graph in the background after setup."""

    try:
        base_payload = runtime.home_graph_base_payload()
        snapshot = await async_build_home_graph_snapshot(
            runtime.hass,
            runtime.entry,
            base_payload["installationId"],
            base_payload.get("knowledgeSpaceId"),
            include_unexposed=runtime.include_unexposed_entities,
        )
        response = await runtime.client.home_graph_sync(snapshot)
        runtime.async_apply_home_graph_response(response, sync=True)
        _log_home_graph_sync(snapshot, response, trigger="startup")
        await runtime.async_refresh_home_graph()
    except GoodVibesClientError as err:
        runtime.home_graph_last_error = str(err)
        async_dispatcher_send(runtime.hass, runtime.signal)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a GoodVibes config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime = hass.data[DOMAIN].pop(entry.entry_id, None)
        if runtime and runtime.unsubscribe_event:
            runtime.unsubscribe_event()
        if runtime and runtime.unsubscribe_auto_sync:
            runtime.unsubscribe_auto_sync()
        if not any(
            isinstance(value, GoodVibesRuntimeData)
            for value in hass.data.get(DOMAIN, {}).values()
        ):
            async_unload_frontend_panel(hass)
    return unload_ok
