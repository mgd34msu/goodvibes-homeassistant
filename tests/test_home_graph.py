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


async def test_entity_snapshot_carries_causal_provenance(hass, entry):
    """With a resolver, an entity snapshot carries its state's attributed cause."""

    from homeassistant.core import Context

    hass.states.async_set(
        "light.kitchen", "on", {"friendly_name": "Kitchen"}, context=Context(user_id="u9")
    )
    await hass.async_block_till_done()

    registry_entity = SimpleNamespace(
        entity_id="light.kitchen",
        unique_id="k-1",
        platform="demo",
        device_id=None,
        area_id=None,
        name=None,
        original_name="Kitchen",
        translation_key=None,
        entity_category=None,
        disabled_by=None,
        hidden_by=None,
        labels=None,
        aliases=None,
    )

    def _resolver(context):
        if context is None:
            return None
        return {"contextId": context.id, "cause": {"kind": "user", "userId": context.user_id}}

    snapshot = home_graph._entity_snapshot(hass, registry_entity, _resolver)

    assert snapshot["provenance"]["cause"] == {"kind": "user", "userId": "u9"}
    # The cause is mirrored into metadata for a metadata-only graph indexer.
    assert snapshot["metadata"]["cause"] == {"kind": "user", "userId": "u9"}


async def test_entity_snapshot_omits_provenance_without_resolver(hass, entry):
    """No resolver means no fabricated provenance field."""

    hass.states.async_set("light.kitchen", "on")
    await hass.async_block_till_done()

    registry_entity = SimpleNamespace(
        entity_id="light.kitchen",
        unique_id="k-1",
        platform="demo",
        device_id=None,
        area_id=None,
        name=None,
        original_name="Kitchen",
        translation_key=None,
        entity_category=None,
        disabled_by=None,
        hidden_by=None,
        labels=None,
        aliases=None,
    )

    snapshot = home_graph._entity_snapshot(hass, registry_entity)
    assert "provenance" not in snapshot


def test_state_timestamp_absent_state_is_none():
    """A missing state yields no timestamp rather than a fabricated one."""

    assert home_graph._state_timestamp(None, "last_changed") is None


def _registry_fixtures():
    """Two entities, two devices, two areas across an exposed/unexposed split."""

    entities = [
        SimpleNamespace(
            entity_id="light.kitchen", device_id="dev-kitchen", area_id=None
        ),
        SimpleNamespace(
            entity_id="light.hidden", device_id="dev-hidden", area_id="area-hidden"
        ),
    ]
    devices = [
        SimpleNamespace(id="dev-kitchen", area_id="area-kitchen"),
        SimpleNamespace(id="dev-hidden", area_id="area-hidden"),
    ]
    areas = [
        SimpleNamespace(id="area-kitchen"),
        SimpleNamespace(id="area-hidden"),
    ]
    return {"entities": entities, "devices": devices, "areas": areas}


async def _patched_snapshot(hass, entry, *, include_unexposed, exposed):
    """Build a snapshot over the fixtures with a controlled exposure boundary."""

    fixtures = _registry_fixtures()

    def _fake_registry_items(_registry, attr):
        return fixtures.get(attr, [])

    def _fake_should_expose(_hass, _assistant, entity_id):
        return entity_id in exposed

    with (
        patch.object(home_graph, "async_get_integration", None),
        patch.object(home_graph, "_registry_items", _fake_registry_items),
        patch.object(home_graph, "async_should_expose", _fake_should_expose),
    ):
        return await home_graph.async_build_home_graph_snapshot(
            hass,
            entry,
            installation_id="inst-1",
            knowledge_space_id=None,
            include_unexposed=include_unexposed,
        )


async def test_snapshot_filters_to_exposed_entities_by_default(hass, entry):
    """Only entities exposed to assistants reach the default snapshot."""

    snapshot = await _patched_snapshot(
        hass, entry, include_unexposed=False, exposed={"light.kitchen"}
    )

    entity_ids = {item["entityId"] for item in snapshot["entities"]}
    assert entity_ids == {"light.kitchen"}


async def test_snapshot_prunes_devices_and_areas_to_included_entities(hass, entry):
    """Devices/areas survive only when an included entity resolves to them."""

    snapshot = await _patched_snapshot(
        hass, entry, include_unexposed=False, exposed={"light.kitchen"}
    )

    device_ids = {item["id"] for item in snapshot["devices"]}
    area_ids = {item["id"] for item in snapshot["areas"]}
    # light.kitchen has no area of its own; it inherits its device's area.
    assert device_ids == {"dev-kitchen"}
    assert area_ids == {"area-kitchen"}
    assert "dev-hidden" not in device_ids
    assert "area-hidden" not in area_ids


async def test_snapshot_include_unexposed_keeps_everything(hass, entry):
    """The toggle carries the whole registry regardless of exposure."""

    snapshot = await _patched_snapshot(
        hass, entry, include_unexposed=True, exposed=set()
    )

    entity_ids = {item["entityId"] for item in snapshot["entities"]}
    device_ids = {item["id"] for item in snapshot["devices"]}
    area_ids = {item["id"] for item in snapshot["areas"]}
    assert entity_ids == {"light.kitchen", "light.hidden"}
    assert device_ids == {"dev-kitchen", "dev-hidden"}
    assert area_ids == {"area-kitchen", "area-hidden"}
