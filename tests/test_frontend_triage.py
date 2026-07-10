"""Tests for Home Graph issue triage after the Python engine's retirement.

``_async_triage_home_graph_issues`` used to run its own LLM classification
loop with a Store-backed decision cache (see
docs/triage-engine-comparison.md). It is now a thin proxy onto the daemon's
``POST /home-graph/refinement/run`` ``triage`` mode (SDK decision record
2026-07-07-home-graph-issue-triage.md) — the daemon owns the triage prompt,
confidence gate, and decision cache. These tests cover the capability gate
(happy path, an unconfigured daemon, and an older daemon that 404s on the
``triage`` input) and that panel-supplied options are forwarded correctly.
"""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.goodvibes.client import GoodVibesSurfaceMissingError
from custom_components.goodvibes.const import DOMAIN
from custom_components.goodvibes.data import GoodVibesRuntimeData
from custom_components.goodvibes.frontend import _async_triage_home_graph_issues

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


class _FakeTriageClient:
    """Records the ``refinement/run`` call and returns a scripted response.

    Any other client method (``home_graph_status``, ``home_graph_issues``,
    etc., reached via ``async_refresh_home_graph``) returns a benign
    ``{"ok": True}`` so the runtime refresh after a successful triage run does
    not need its own fixture.
    """

    def __init__(self, *, response=None, raise_error=None):
        self.daemon_url = DAEMON
        self.calls: list[dict] = []
        self._response = response
        self._raise_error = raise_error

    async def home_graph_refinement_run(self, payload):
        self.calls.append(payload)
        if self._raise_error is not None:
            raise self._raise_error
        return self._response

    def __getattr__(self, name: str):
        async def _call(*args, **kwargs):
            return {"ok": True}

        return _call


@pytest.fixture
def make_runtime(hass):
    """Register a fake runtime bound to a scripted daemon client."""

    def _make(client) -> GoodVibesRuntimeData:
        entry = MockConfigEntry(domain=DOMAIN, unique_id=DAEMON, data=ENTRY_DATA)
        entry.add_to_hass(hass)
        rt = GoodVibesRuntimeData(
            hass=hass,
            entry=entry,
            client=client,
            event_type="goodvibes_message",
            home_graph_enabled=True,
            installation_id="inst",
            knowledge_space_id=None,
        )
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = rt
        return rt

    return _make


async def test_triage_happy_path_delegates_to_refinement_run(make_runtime):
    """A configured daemon's triage result is applied and returned as-is."""

    triage_result = {
        "ok": True,
        "spaceId": "space-1",
        "configured": True,
        "processed": 3,
        "skipped": 1,
        "applied": 2,
        "reviewed": 2,
        "decisions": [{"issueId": "i1", "action": "reject", "confidence": 92}],
        "remaining": 4,
        "minConfidence": 85,
    }
    client = _FakeTriageClient(response={"ok": True, "triage": triage_result})
    runtime = make_runtime(client)

    result = await _async_triage_home_graph_issues(runtime, {})

    assert result == triage_result
    assert len(client.calls) == 1
    payload = client.calls[0]
    assert payload["installationId"] == "inst"
    assert payload["triage"] == {
        "minConfidence": 85,
        "limit": 25,
        "chunkSize": 25,
        "force": False,
        "skipIssueIds": [],
        "reviewer": "homeassistant:auto-triage",
    }
    assert payload["skipGapRefinement"] is True
    # A real result was applied to runtime state and the graph was refreshed
    # (the fake client's home_graph_status/home_graph_issues calls returned
    # {"ok": True} without raising).
    assert runtime.home_graph_last_response == {"ok": True, "triage": triage_result}


async def test_triage_unconfigured_daemon_falls_back_honestly(make_runtime):
    """``configured: false`` is reported honestly, never re-engined locally."""

    client = _FakeTriageClient(
        response={
            "ok": True,
            "triage": {
                "ok": True,
                "configured": False,
                "reason": "triage-llm-not-configured",
            },
        }
    )
    runtime = make_runtime(client)

    result = await _async_triage_home_graph_issues(runtime, {})

    assert result["ok"] is True
    assert result["configured"] is False
    assert result["reason"] == "triage-llm-not-configured"
    assert result["processed"] == 0
    assert result["skipped"] == 0
    assert result["applied"] == 0
    assert result["reviewed"] == 0
    assert result["decisions"] == []
    assert result["remaining"] is None


async def test_triage_older_daemon_404_falls_back_honestly(make_runtime):
    """A pre-triage daemon 404s on the ``triage`` input; no local re-engine runs."""

    client = _FakeTriageClient(
        raise_error=GoodVibesSurfaceMissingError("not found", status=404)
    )
    runtime = make_runtime(client)

    result = await _async_triage_home_graph_issues(
        runtime, {"limit": 10, "force": True}
    )

    assert result["ok"] is True
    assert result["configured"] is False
    assert result["reason"] == "daemon-triage-not-supported"
    assert result["decisions"] == []
    assert len(client.calls) == 1
    # The 404 short-circuits before any Home Graph refresh call is needed.
    assert client.calls[0]["triage"]["limit"] == 10
    assert client.calls[0]["triage"]["force"] is True


async def test_triage_missing_triage_key_falls_back_honestly(make_runtime):
    """A response with no ``triage`` object at all is treated as unsupported."""

    client = _FakeTriageClient(response={"ok": True})
    runtime = make_runtime(client)

    result = await _async_triage_home_graph_issues(runtime, {})

    assert result["configured"] is False
    assert result["reason"] == "daemon-triage-not-supported"


async def test_triage_forwards_limit_force_and_skip_issue_ids(make_runtime):
    """Panel-supplied limit/force/skipIssueIds are forwarded in the triage body."""

    client = _FakeTriageClient(
        response={
            "ok": True,
            "triage": {
                "ok": True,
                "configured": True,
                "processed": 0,
                "skipped": 0,
                "applied": 0,
                "reviewed": 0,
                "decisions": [],
                "remaining": 0,
                "minConfidence": 85,
            },
        }
    )
    runtime = make_runtime(client)

    await _async_triage_home_graph_issues(
        runtime,
        {"limit": 5, "force": True, "skipIssueIds": ["a", "b"]},
    )

    payload = client.calls[0]
    assert payload["triage"]["limit"] == 5
    assert payload["triage"]["force"] is True
    assert payload["triage"]["skipIssueIds"] == ["a", "b"]
