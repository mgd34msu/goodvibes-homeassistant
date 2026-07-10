"""Tests for the perception-trigger manager."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.goodvibes.perception import (
    GoodVibesPerceptionManager,
    perception_entity_ids,
)


def _make_runtime(hass):
    """Build a duck-typed runtime the perception manager can drive."""

    entry = SimpleNamespace(
        async_create_background_task=lambda hass, coro, name=None: hass.async_create_task(
            coro
        )
    )
    return SimpleNamespace(
        hass=hass,
        include_unexposed_entities=True,
        client=SimpleNamespace(
            run_agent=AsyncMock(return_value={"sessionId": "s1", "agentId": "a1"})
        ),
        entry=entry,
        async_apply_submission_response=MagicMock(),
        last_error=None,
    )


def test_perception_entity_ids_dedups_and_strips():
    ids = perception_entity_ids(
        {"perception_entities": ["light.a", "light.a", " light.b ", ""]}
    )
    assert ids == ["light.a", "light.b"]


async def test_value_change_starts_attributed_session(hass):
    runtime = _make_runtime(hass)
    hass.states.async_set("binary_sensor.door", "off", {"friendly_name": "Front Door"})
    await hass.async_block_till_done()

    manager = GoodVibesPerceptionManager(hass, runtime, ["binary_sensor.door"])
    manager.async_start()

    hass.states.async_set("binary_sensor.door", "on", {"friendly_name": "Front Door"})
    await hass.async_block_till_done()

    assert runtime.client.run_agent.await_count == 1
    payload = runtime.client.run_agent.await_args.args[0]
    # The session is attributed and carries the triggering context.
    assert payload["displayName"] == "GoodVibes Perception"
    assert payload["entityId"] == "binary_sensor.door"
    assert payload["context"]["oldState"] == "off"
    assert payload["context"]["newState"] == "on"
    assert payload["context"]["trigger"] == "homeassistant_state_change"
    assert "Front Door" in payload["task"]
    runtime.async_apply_submission_response.assert_called_once()

    manager.async_stop()


async def test_attribute_only_change_does_not_trigger(hass):
    runtime = _make_runtime(hass)
    hass.states.async_set("binary_sensor.door", "on", {"friendly_name": "Door"})
    await hass.async_block_till_done()

    manager = GoodVibesPerceptionManager(hass, runtime, ["binary_sensor.door"])
    manager.async_start()

    # Same state value, different attribute -> not an observation.
    hass.states.async_set("binary_sensor.door", "on", {"friendly_name": "Door 2"})
    await hass.async_block_till_done()

    assert runtime.client.run_agent.await_count == 0
    manager.async_stop()


async def test_unavailable_transition_is_ignored(hass):
    runtime = _make_runtime(hass)
    hass.states.async_set("binary_sensor.door", "on")
    await hass.async_block_till_done()

    manager = GoodVibesPerceptionManager(hass, runtime, ["binary_sensor.door"])
    manager.async_start()

    hass.states.async_set("binary_sensor.door", "unavailable")
    await hass.async_block_till_done()

    assert runtime.client.run_agent.await_count == 0
    manager.async_stop()


async def test_rate_limit_suppresses_rapid_repeats(hass):
    runtime = _make_runtime(hass)
    hass.states.async_set("binary_sensor.door", "off")
    await hass.async_block_till_done()

    manager = GoodVibesPerceptionManager(
        hass, runtime, ["binary_sensor.door"], min_interval_s=100
    )
    manager.async_start()

    hass.states.async_set("binary_sensor.door", "on")
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.door", "off")
    await hass.async_block_till_done()

    # The second change lands inside the min interval and is suppressed.
    assert runtime.client.run_agent.await_count == 1
    manager.async_stop()


async def test_stop_unsubscribes(hass):
    runtime = _make_runtime(hass)
    hass.states.async_set("binary_sensor.door", "off")
    await hass.async_block_till_done()

    manager = GoodVibesPerceptionManager(hass, runtime, ["binary_sensor.door"])
    manager.async_start()
    manager.async_stop()

    hass.states.async_set("binary_sensor.door", "on")
    await hass.async_block_till_done()

    assert runtime.client.run_agent.await_count == 0
