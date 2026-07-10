"""Entry lifecycle tests: the auto-sync task is scoped to the config entry."""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.goodvibes as gv
from custom_components.goodvibes import GoodVibesRuntimeData
from custom_components.goodvibes.const import DOMAIN

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


def _make_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DAEMON, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    return entry


def _enter_isolation(hass, stack: ExitStack) -> None:
    """Stub out network and platform work so setup exercises only lifecycle."""

    stack.enter_context(patch.object(gv, "async_setup_frontend", AsyncMock()))
    stack.enter_context(patch.object(gv, "_async_auto_sync_home_graph", AsyncMock()))
    # The coordinator's first refresh runs runtime.async_refresh; stub the manifest
    # fetch and the refresh so setup exercises only lifecycle, not the daemon.
    stack.enter_context(
        patch.object(GoodVibesRuntimeData, "async_fetch_manifest", AsyncMock())
    )
    stack.enter_context(
        patch.object(GoodVibesRuntimeData, "async_refresh", AsyncMock())
    )
    stack.enter_context(
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            AsyncMock(return_value=True),
        )
    )
    stack.enter_context(
        patch.object(
            hass.config_entries,
            "async_unload_platforms",
            AsyncMock(return_value=True),
        )
    )


async def test_auto_sync_task_is_scoped_to_the_entry(hass):
    """Setup schedules the auto-sync through entry.async_create_background_task."""

    entry = _make_entry(hass)
    assert hass.is_running

    with ExitStack() as stack:
        _enter_isolation(hass, stack)
        spy = stack.enter_context(
            patch.object(
                entry,
                "async_create_background_task",
                wraps=entry.async_create_background_task,
            )
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert spy.called
    # The task is named for and tracked by the entry, so Home Assistant cancels
    # it on unload/reload instead of letting it outlive the entry.
    task_name = spy.call_args.kwargs["name"]
    assert entry.entry_id in task_name


async def test_reload_completes_and_stays_loaded(hass):
    """Reloading the entry unloads and sets up again without error."""

    entry = _make_entry(hass)

    with ExitStack() as stack:
        _enter_isolation(hass, stack)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED

        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
