"""Tests for consent-gated habit mining.

Detection is a pure function tested directly; the store's bounds, the automation
config a proposal produces, the miner's recording, and the actual automation
creation are exercised separately.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.yaml import load_yaml

from custom_components.goodvibes.habits import (
    GoodVibesHabitMiner,
    HabitObservationStore,
    Observation,
    async_create_automation_from_config,
    detect_habits,
    state_to_service,
)

# 2026-07-06/07/08 are Mon/Tue/Wed (a weekday run); 2026-07-11/12 are Sat/Sun.
# Times are kept inside a single 30-minute time-of-day bucket (07:00-07:29).
_MON = datetime(2026, 7, 6, 7, 5)
_TUE = datetime(2026, 7, 7, 7, 10)
_WED = datetime(2026, 7, 8, 7, 15)
_SAT = datetime(2026, 7, 11, 9, 0)
_SUN = datetime(2026, 7, 12, 9, 5)


def test_state_to_service_maps_safe_reproductions():
    assert state_to_service("light.k", "on") == ("light", "turn_on")
    assert state_to_service("switch.k", "off") == ("switch", "turn_off")
    assert state_to_service("cover.garage", "open") == ("cover", "open_cover")
    assert state_to_service("lock.front", "locked") == ("lock", "lock")
    # A sensor value has no safe reproducing service.
    assert state_to_service("sensor.temp", "21.5") is None
    assert state_to_service("light.k", "colorloop") is None


def test_detect_habits_finds_a_weekday_pattern():
    """Three weekday mornings of the same change become one proposal."""

    observations = [
        Observation("light.kitchen", "on", _MON),
        Observation("light.kitchen", "on", _TUE),
        Observation("light.kitchen", "on", _WED),
    ]
    proposals = detect_habits(
        observations,
        friendly_names={"light.kitchen": "Kitchen Light"},
    )
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.entity_id == "light.kitchen"
    assert proposal.state == "on"
    assert proposal.day_type == "weekday"
    assert proposal.distinct_days == 3
    assert proposal.time.startswith("07:") or proposal.time.startswith("06:")

    config = proposal.automation_config()
    assert config["action"][0]["service"] == "light.turn_on"
    assert config["action"][0]["target"] == {"entity_id": "light.kitchen"}
    assert config["trigger"][0]["platform"] == "time"
    assert config["condition"][0]["weekday"] == ["mon", "tue", "wed", "thu", "fri"]
    assert config["id"] == f"goodvibes_habit_{proposal.proposal_id}"


def test_detect_habits_respects_thresholds():
    """A pattern seen on too few distinct days is not proposed."""

    observations = [
        Observation("light.kitchen", "on", _MON),
        Observation("light.kitchen", "on", _MON + timedelta(minutes=5)),
    ]
    # Two occurrences but only one distinct day -> below the distinct-day floor.
    assert detect_habits(observations) == []


def test_detect_habits_ignores_non_actionable_entities():
    """Sensor value changes never become control proposals."""

    observations = [
        Observation("sensor.temperature", "21.5", _MON),
        Observation("sensor.temperature", "21.6", _TUE),
        Observation("sensor.temperature", "21.7", _WED),
    ]
    assert detect_habits(observations) == []


def test_detect_habits_weekend_day_type():
    """Weekend occurrences produce a weekend-conditioned proposal."""

    observations = [
        Observation("switch.coffee", "on", _SAT),
        Observation("switch.coffee", "on", _SUN),
        Observation("switch.coffee", "on", _SAT + timedelta(days=7)),
    ]
    proposals = detect_habits(observations)
    assert len(proposals) == 1
    assert proposals[0].day_type == "weekend"
    assert proposals[0].automation_config()["condition"][0]["weekday"] == ["sat", "sun"]


def test_observation_store_bounds_by_age():
    """Observations past the retention window are pruned."""

    store = HabitObservationStore(timedelta(days=2), max_observations=100)
    now = datetime(2026, 7, 10, 12, 0)
    store.record("light.k", "on", now - timedelta(days=5))
    store.record("light.k", "on", now)
    store.prune(now)
    assert len(store) == 1
    assert store.observations()[0].when == now


def test_observation_store_bounds_by_count():
    """The count cap drops the oldest observations."""

    store = HabitObservationStore(timedelta(days=365), max_observations=2)
    base = datetime(2026, 7, 10, 12, 0)
    store.record("light.k", "on", base)
    store.record("light.k", "off", base + timedelta(minutes=1))
    store.record("light.k", "on", base + timedelta(minutes=2))
    assert len(store) == 2
    # The very first record was evicted.
    assert store.observations()[0].state == "off"


async def test_miner_records_actionable_exposed_changes(hass):
    """The miner records controllable value changes and skips the rest."""

    runtime = SimpleNamespace(include_unexposed_entities=True)
    miner = GoodVibesHabitMiner(
        hass, runtime, retention_days=30, on_proposals=AsyncMock()
    )
    miner.async_start()
    try:
        hass.states.async_set("light.kitchen", "off")
        await hass.async_block_till_done()
        hass.states.async_set("light.kitchen", "on")
        await hass.async_block_till_done()
        # A sensor is not controllable, so it is never stored.
        hass.states.async_set("sensor.temperature", "21.5")
        await hass.async_block_till_done()
        hass.states.async_set("sensor.temperature", "21.6")
        await hass.async_block_till_done()

        entities = {obs.entity_id for obs in miner.store.observations()}
        assert "light.kitchen" in entities
        assert "sensor.temperature" not in entities
        # Too little history to propose anything yet.
        assert miner.analyze() == []
    finally:
        miner.async_stop()


async def test_create_automation_writes_and_reloads(hass, tmp_path):
    """Accepting a proposal appends a standard automation and reloads."""

    # Isolate the automations store to this test's temp config directory.
    hass.config.config_dir = str(tmp_path)
    reloaded: list[int] = []
    hass.services.async_register(
        "automation", "reload", lambda call: reloaded.append(1)
    )
    config = {
        "id": "goodvibes_habit_abc123",
        "alias": "GoodVibes habit: Kitchen Light turn_on at 07:00 on weekdays",
        "trigger": [{"platform": "time", "at": "07:00:00"}],
        "condition": [{"condition": "time", "weekday": ["mon"]}],
        "action": [{"service": "light.turn_on", "target": {"entity_id": "light.kitchen"}}],
        "mode": "single",
    }

    automation_id = await async_create_automation_from_config(hass, config)
    assert automation_id == "goodvibes_habit_abc123"
    assert reloaded == [1]

    stored = load_yaml(hass.config.path("automations.yaml"))
    assert isinstance(stored, list)
    assert stored[0]["id"] == "goodvibes_habit_abc123"

    # Accepting the same proposal twice is refused.
    with pytest.raises(HomeAssistantError):
        await async_create_automation_from_config(hass, config)
