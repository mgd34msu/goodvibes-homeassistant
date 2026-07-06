"""Config-flow tests: the happy path and each typed classification branch."""

from __future__ import annotations

import aiohttp
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.goodvibes.const import DOMAIN

DAEMON = "http://127.0.0.1:3210"

USER_INPUT = {
    "daemon_url": DAEMON,
    "daemon_token": "tok",
    "webhook_secret": "secret",
    "event_type": "goodvibes_message",
    "home_graph_enabled": True,
    "installation_id": "",
    "knowledge_space_id": "",
}


def _mock_all_ok(aioclient_mock) -> None:
    aioclient_mock.get(
        f"{DAEMON}/status", json={"status": "running", "version": "1.2.0"}
    )
    aioclient_mock.get(f"{DAEMON}/api/homeassistant/health", json={"ok": True})
    aioclient_mock.get(
        f"{DAEMON}/api/homeassistant/home-graph/status",
        json={"ok": True, "sourceCount": 0},
    )
    aioclient_mock.post(
        f"{DAEMON}/api/channels/actions/homeassistant/homeassistant-manifest",
        json={
            "actionId": "homeassistant-manifest",
            "surface": "homeassistant",
            "result": {
                "device": {
                    "name": "GoodVibes Daemon",
                    "model": "GoodVibes Daemon",
                    "identifiers": ["goodvibes:goodvibes-daemon"],
                }
            },
        },
    )


async def _run_user_flow(hass) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(USER_INPUT)
    )


async def test_user_flow_success_creates_entry(hass, aioclient_mock):
    """A reachable, enabled daemon creates a config entry titled from manifest."""

    _mock_all_ok(aioclient_mock)
    result = await _run_user_flow(hass)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "GoodVibes Daemon"
    assert result["data"]["daemon_url"] == DAEMON


async def test_user_flow_invalid_auth(hass, aioclient_mock):
    """A rejected bearer token (401) classifies as invalid_auth."""

    aioclient_mock.get(f"{DAEMON}/status", status=401, text="Unauthorized")
    result = await _run_user_flow(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_surface_missing(hass, aioclient_mock):
    """A daemon reporting its Home Assistant surface off classifies as missing."""

    aioclient_mock.get(
        f"{DAEMON}/status", json={"status": "running", "version": "1.2.0"}
    )
    aioclient_mock.get(f"{DAEMON}/api/homeassistant/health", json={"ok": False})
    result = await _run_user_flow(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "surface_missing"}


async def test_user_flow_cannot_connect(hass, aioclient_mock):
    """An unreachable daemon classifies as cannot_connect."""

    aioclient_mock.get(f"{DAEMON}/status", exc=aiohttp.ClientError())
    result = await _run_user_flow(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_duplicate_daemon_aborts(hass, aioclient_mock):
    """A second entry for the same daemon URL aborts as already_configured."""

    MockConfigEntry(
        domain=DOMAIN, unique_id=DAEMON, data=dict(USER_INPUT)
    ).add_to_hass(hass)
    _mock_all_ok(aioclient_mock)
    result = await _run_user_flow(hass)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
