"""Tests for the Home Graph websocket action dispatch table.

frontend.py's ``_handle_home_graph_action`` used to be a 260-line if/elif
chain over 26 actions; it is now a dict dispatch table (``_ACTION_HANDLERS``).
These tests cover the wire contract that refactor had to preserve: every
action the panel JS calls still resolves to a handler, an unknown action
still raises the same error, a disabled Home Graph entry still refuses every
action the same way, and a couple of representative actions (a plain
read, and ``ingest_url`` which now delegates to the service's shared
implementation instead of a local duplicate) still return the same shape.
"""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.goodvibes.const import DOMAIN
from custom_components.goodvibes.data import GoodVibesRuntimeData
from custom_components.goodvibes.frontend import (
    SUPPORTED_ACTIONS,
    _ACTION_HANDLERS,
    _handle_home_graph_action,
)

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


class _FakeClient:
    """Records every Home Graph call it receives and returns a canned reply."""

    def __init__(self) -> None:
        self.daemon_url = DAEMON
        self.calls: list[tuple[str, dict]] = []

    async def home_graph_browse(self, payload):
        self.calls.append(("browse", payload))
        return {"ok": True, "records": []}

    async def home_graph_sync(self, snapshot):
        self.calls.append(("sync", snapshot))
        return {"ok": True, "status": "synced"}

    async def home_graph_ingest_url(self, payload):
        self.calls.append(("ingest_url", payload))
        return {"ok": True, "sourceId": "src-1"}

    def __getattr__(self, name: str):
        async def _call(*args, **kwargs):
            return {"ok": True}

        return _call


def _runtime(hass, client: _FakeClient, *, home_graph_enabled=True) -> GoodVibesRuntimeData:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DAEMON, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    rt = GoodVibesRuntimeData(
        hass=hass,
        entry=entry,
        client=client,
        event_type="goodvibes_message",
        home_graph_enabled=home_graph_enabled,
        installation_id="inst",
        knowledge_space_id=None,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = rt
    return rt


def test_every_supported_action_has_a_handler():
    """Every action the websocket schema allows resolves to a dispatch entry."""

    missing = SUPPORTED_ACTIONS - set(_ACTION_HANDLERS)
    assert missing == set()


async def test_unsupported_action_raises_the_same_error(hass):
    """An action outside the dispatch table is refused with the original message."""

    from homeassistant.exceptions import HomeAssistantError

    runtime = _runtime(hass, _FakeClient())
    try:
        await _handle_home_graph_action(hass, runtime, "not_a_real_action", {})
        raise AssertionError("expected HomeAssistantError")
    except HomeAssistantError as err:
        assert str(err) == "Unsupported Home Graph action: not_a_real_action"


async def test_disabled_home_graph_refuses_every_action(hass):
    """A config entry with Home Graph disabled refuses before any dispatch."""

    from homeassistant.exceptions import HomeAssistantError

    runtime = _runtime(hass, _FakeClient(), home_graph_enabled=False)
    try:
        await _handle_home_graph_action(hass, runtime, "browse", {})
        raise AssertionError("expected HomeAssistantError")
    except HomeAssistantError as err:
        assert str(err) == "Home Graph is disabled for this GoodVibes entry"


async def test_browse_action_passes_through_the_client_response(hass):
    """A plain read action still returns the daemon client's response as-is."""

    client = _FakeClient()
    runtime = _runtime(hass, client)

    result = await _handle_home_graph_action(hass, runtime, "browse", {"limit": 5})

    assert result == {"ok": True, "records": []}
    action, payload = client.calls[0]
    assert action == "browse"
    assert payload["limit"] == 5
    assert payload["installationId"] == "inst"


async def test_ingest_url_delegates_to_the_shared_service_implementation(hass):
    """``ingest_url`` now calls services.async_ingest_url_action, not a copy."""

    client = _FakeClient()
    runtime = _runtime(hass, client)

    result = await _handle_home_graph_action(
        hass, runtime, "ingest_url", {"url": "https://example.com/doc"}
    )

    assert result == {"ok": True, "sourceId": "src-1"}
    call_names = [name for name, _ in client.calls]
    # The shared implementation syncs Home Assistant context (a "sync" call)
    # before the ingest itself, same as the pre-refactor branch did.
    assert call_names == ["sync", "ingest_url"]
    ingest_payload = client.calls[-1][1]
    assert ingest_payload["url"] == "https://example.com/doc"
