"""Tests for the Home Graph snapshot builder's state provenance fields.

The snapshot carries the per-entity observation timestamps (``lastChanged`` /
``lastUpdated``) plus a snapshot-level ``metadata.generatedAt`` so that an answer
built from a snapshotted state can cite when the state was observed rather than
presenting a value with no time behind it.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.goodvibes import home_graph


@pytest.fixture(name="entry")
def _entry():
    return SimpleNamespace(entry_id="entry-1")


async def test_entity_snapshot_carries_state_and_observation_timestamps(hass, entry):
    """A snapshotted entity keeps its state plus last_changed/last_updated."""

    hass.states.async_set(
        "cover.garage_door",
        "open",
        {"friendly_name": "Garage Door"},
    )
    await hass.async_block_till_done()

    registry_entity = SimpleNamespace(
        entity_id="cover.garage_door",
        unique_id="garage-door-1",
        platform="demo",
        device_id=None,
        area_id=None,
        name=None,
        original_name="Garage Door",
        translation_key=None,
        entity_category=None,
        disabled_by=None,
        hidden_by=None,
        labels=None,
        aliases=None,
    )

    snapshot = home_graph._entity_snapshot(hass, registry_entity)

    assert snapshot["entityId"] == "cover.garage_door"
    assert snapshot["state"] == "open"
    # Provenance: the value never travels without the time it was observed.
    assert "lastChanged" in snapshot
    assert "lastUpdated" in snapshot
    assert snapshot["lastChanged"].startswith("20") or "T" in snapshot["lastChanged"]
    assert "T" in snapshot["lastUpdated"]


async def test_snapshot_records_generation_timestamp(hass, entry):
    """The full snapshot stamps a snapshot-level observation time."""

    with patch.object(home_graph, "async_get_integration", None):
        snapshot = await home_graph.async_build_home_graph_snapshot(
            hass,
            entry,
            installation_id="inst-1",
            knowledge_space_id=None,
        )

    assert snapshot["metadata"]["source"] == "homeassistant"
    generated_at = snapshot["metadata"]["generatedAt"]
    assert isinstance(generated_at, str) and generated_at
    assert "T" in generated_at


def test_state_timestamp_absent_state_is_none():
    """A missing state yields no timestamp rather than a fabricated one."""

    assert home_graph._state_timestamp(None, "last_changed") is None
