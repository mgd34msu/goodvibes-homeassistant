"""Stage 3: smoke tests for the extracted, module-level service handlers.

Every service that used to be a closure inside ``async_setup`` is now a
module-level function in ``services.py``. These tests exercise each handler in
isolation against a fake daemon client, asserting it resolves its runtime,
builds a payload, and dispatches to the right client method without raising.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import Context, ServiceCall
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.goodvibes import services as svc
from custom_components.goodvibes.const import DOMAIN
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


class _FakeClient:
    """Records every daemon call and returns a benign response."""

    def __init__(self) -> None:
        self.daemon_url = DAEMON
        self.calls: dict[str, tuple] = {}

    def __getattr__(self, name: str):
        async def _call(*args, **kwargs):
            self.calls[name] = (args, kwargs)
            return {"ok": True}

        return _call


@pytest.fixture
def runtime(hass):
    """Register a fake runtime and stub the snapshot builder."""

    entry = MockConfigEntry(domain=DOMAIN, unique_id=DAEMON, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    rt = GoodVibesRuntimeData(
        hass=hass,
        entry=entry,
        client=_FakeClient(),
        event_type="goodvibes_message",
        home_graph_enabled=True,
        installation_id="inst",
        knowledge_space_id=None,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = rt
    with patch.object(
        svc,
        "async_build_home_graph_snapshot",
        return_value={"installationId": "inst", "knowledgeSpaceId": "ks"},
    ):
        yield rt


async def _call(hass, name: str, data: dict) -> dict:
    handler = getattr(svc, name)
    return await handler(ServiceCall(hass, DOMAIN, name, dict(data)))


async def _call_as(hass, name: str, data: dict, user_id: str) -> dict:
    """Invoke a handler as a specific user (a call carrying a user context)."""

    handler = getattr(svc, name)
    return await handler(
        ServiceCall(hass, DOMAIN, name, dict(data), context=Context(user_id=user_id))
    )


# (handler name, minimal valid data, expected daemon client method)
SMOKE = [
    ("async_prompt", {"message": "hi"}, "prompt"),
    ("async_run_agent", {"task": "do", "message": "do"}, "run_agent"),
    ("async_cancel", {"run_id": "r1"}, "control_command"),
    ("async_call_tool", {"tool": "homeassistant_states", "input": {}}, "call_tool"),
    ("async_sync_home_graph", {}, "home_graph_sync"),
    ("async_ingest_url", {"url": "http://x/y"}, "home_graph_ingest_url"),
    ("async_ingest_note", {"note": "n"}, "home_graph_ingest_note"),
    ("async_ingest_artifact", {"path": "/p.pdf"}, "home_graph_ingest_artifact"),
    (
        "async_link_knowledge",
        {"source_id": "s", "target_kind": "device", "target_id": "d"},
        "home_graph_link",
    ),
    (
        "async_unlink_knowledge",
        {"source_id": "s", "target_kind": "device", "target_id": "d"},
        "home_graph_unlink",
    ),
    ("async_ask_home_graph", {"query": "q"}, "home_graph_ask"),
    ("async_device_passport", {"device_id": "d"}, "home_graph_device_passport"),
    ("async_room_page", {"area_id": "a"}, "home_graph_room_page"),
    ("async_home_graph_packet", {"packet_type": "room"}, "home_graph_packet"),
    ("async_home_graph_issues", {}, "home_graph_issues"),
    ("async_review_fact", {"action": "reject", "issue_id": "i"}, "home_graph_review_fact"),
    ("async_home_graph_sources", {}, "home_graph_sources"),
    ("async_home_graph_pages", {}, "home_graph_pages"),
    ("async_home_graph_browse", {}, "home_graph_browse"),
    ("async_home_graph_map", {}, "home_graph_map"),
    ("async_home_graph_export", {}, "home_graph_export"),
    ("async_home_graph_import", {"data": {}}, "home_graph_import"),
    ("async_home_graph_reset", {"dry_run": True}, "home_graph_reset"),
    ("async_home_graph_reindex", {}, "home_graph_reindex"),
]


@pytest.mark.parametrize(("name", "data", "method"), SMOKE, ids=[s[0] for s in SMOKE])
async def test_service_handler_dispatches(hass, runtime, name, data, method):
    """Each handler runs, returns a dict, and calls its daemon method."""

    result = await _call(hass, name, data)
    assert isinstance(result, dict)
    assert method in runtime.client.calls


async def test_status_handler_returns_snapshot(hass, runtime):
    """status with no ids refreshes and returns the daemon/tools view."""

    result = await _call(hass, "async_status", {})
    assert set(result) >= {"daemon", "homeassistant", "tools"}


async def test_home_graph_status_handler_shape(hass, runtime):
    """home_graph_status returns the panel status view."""

    result = await _call(hass, "async_home_graph_status", {})
    assert "status" in result and "issues" in result


async def test_ingest_url_builds_url_payload(hass, runtime):
    """ingest_url forwards the url in the daemon payload."""

    await _call(hass, "async_ingest_url", {"url": "http://x/doc"})
    (args, _kwargs) = runtime.client.calls["home_graph_ingest_url"]
    assert args[0]["url"] == "http://x/doc"


async def test_review_fact_requires_action(hass, runtime):
    """review_fact without an action or decision raises."""

    with pytest.raises(HomeAssistantError):
        await _call(hass, "async_review_fact", {"issue_id": "i"})


async def test_cancel_without_target_raises(hass, runtime):
    """cancel with no ids and no active turn raises a helpful error."""

    with pytest.raises(HomeAssistantError):
        await _call(hass, "async_cancel", {})


async def test_mutating_service_rejects_non_admin(hass, runtime, hass_read_only_user):
    """A mutating service called on behalf of a non-admin user is refused."""

    with pytest.raises(Unauthorized):
        await _call_as(hass, "async_prompt", {"message": "hi"}, hass_read_only_user.id)
    assert "prompt" not in runtime.client.calls


async def test_mutating_service_allows_admin(hass, runtime, hass_admin_user):
    """A mutating service called on behalf of an admin user runs normally."""

    result = await _call_as(hass, "async_prompt", {"message": "hi"}, hass_admin_user.id)
    assert isinstance(result, dict)
    assert "prompt" in runtime.client.calls


async def test_mutating_service_allows_no_user_context(hass, runtime):
    """A call with no user context (automation/script) is allowed through."""

    await _call(hass, "async_prompt", {"message": "hi"})
    assert "prompt" in runtime.client.calls


async def test_destructive_reset_rejects_non_admin(hass, runtime, hass_read_only_user):
    """Even a dry-run Home Graph reset is admin-only."""

    with pytest.raises(Unauthorized):
        await _call_as(
            hass, "async_home_graph_reset", {"dry_run": True}, hass_read_only_user.id
        )
    assert "home_graph_reset" not in runtime.client.calls


async def test_read_only_service_allows_non_admin(hass, runtime, hass_read_only_user):
    """Read-only status stays open to a non-admin user."""

    result = await _call_as(
        hass, "async_home_graph_status", {}, hass_read_only_user.id
    )
    assert "status" in result


async def test_entity_control_check_blocks_non_admin_without_permission(
    hass, hass_read_only_user
):
    """The entity guard refuses an entity the calling user cannot control."""

    call = ServiceCall(
        hass,
        DOMAIN,
        "home_graph_packet",
        {},
        context=Context(user_id=hass_read_only_user.id),
    )
    with pytest.raises(Unauthorized):
        await svc._async_verify_entity_control(call, ["light.kitchen"])


async def test_entity_control_check_allows_admin(hass, hass_admin_user):
    """An admin passes the entity guard for any entity."""

    call = ServiceCall(
        hass,
        DOMAIN,
        "home_graph_packet",
        {},
        context=Context(user_id=hass_admin_user.id),
    )
    # No exception: administrators hold control over every entity.
    await svc._async_verify_entity_control(call, ["light.kitchen"])


async def test_entity_control_check_allows_no_user_context(hass):
    """With no user context the entity guard allows the call (trusted caller)."""

    call = ServiceCall(hass, DOMAIN, "home_graph_packet", {})
    await svc._async_verify_entity_control(call, ["light.kitchen"])


async def test_setup_services_registers_all_and_is_idempotent(hass):
    """async_setup_services registers the full service surface once."""

    await svc.async_setup_services(hass)
    registered = hass.services.async_services().get(DOMAIN, {})
    # 26 services: the 24 in the smoke list plus status and home_graph_status.
    assert len(registered) == 26
    for service in ("prompt", "status", "home_graph_status", "sync_home_graph"):
        assert service in registered
    # A second call is a no-op (guarded by the services_registered flag).
    await svc.async_setup_services(hass)
    assert len(hass.services.async_services().get(DOMAIN, {})) == 26
