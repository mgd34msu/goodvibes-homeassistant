"""Tests for the causal-provenance tracker.

The tracker indexes the Home Assistant context chain so a state change can be
attributed to its cause — an automation, script, scene, service call, or user —
and is honest about what the chain cannot tell it (device/integration-originated
changes and broken chains).
"""

from __future__ import annotations

from homeassistant.core import Context

from custom_components.goodvibes.provenance import GoodVibesProvenanceTracker


async def _tracker(hass) -> GoodVibesProvenanceTracker:
    tracker = GoodVibesProvenanceTracker(hass)
    tracker.async_start()
    return tracker


async def test_resolve_attributes_a_user(hass):
    """A context carrying a user id is attributed to that user."""

    tracker = await _tracker(hass)
    try:
        provenance = tracker.resolve(Context(user_id="user-1"))
        assert provenance["cause"] == {"kind": "user", "userId": "user-1"}
        assert provenance["userId"] == "user-1"
    finally:
        tracker.async_stop()


async def test_resolve_attributes_an_automation_up_the_parent_chain(hass):
    """A state change parented to an automation run is attributed to it."""

    tracker = await _tracker(hass)
    try:
        automation_ctx = Context()
        hass.bus.async_fire(
            "automation_triggered",
            {"entity_id": "automation.morning", "name": "Morning"},
            context=automation_ctx,
        )
        await hass.async_block_till_done()

        # The light's state change context is a child of the automation context.
        change_ctx = Context(parent_id=automation_ctx.id)
        provenance = tracker.resolve(change_ctx)

        assert provenance["cause"]["kind"] == "automation"
        assert provenance["cause"]["entityId"] == "automation.morning"
        assert provenance["cause"]["name"] == "Morning"
        assert provenance["parentId"] == automation_ctx.id
    finally:
        tracker.async_stop()


async def test_resolve_attributes_a_service_call(hass):
    """A change parented to a service call is attributed to that call."""

    tracker = await _tracker(hass)
    try:
        service_ctx = Context()
        hass.bus.async_fire(
            "call_service",
            {"domain": "light", "service": "turn_on"},
            context=service_ctx,
        )
        await hass.async_block_till_done()

        provenance = tracker.resolve(Context(parent_id=service_ctx.id))
        assert provenance["cause"]["kind"] == "service_call"
        assert provenance["cause"]["domain"] == "light"
        assert provenance["cause"]["service"] == "turn_on"
    finally:
        tracker.async_stop()


async def test_scene_service_call_is_labelled_scene(hass):
    """Applying a scene (scene.turn_on) is attributed as a scene."""

    tracker = await _tracker(hass)
    try:
        scene_ctx = Context()
        hass.bus.async_fire(
            "call_service",
            {"domain": "scene", "service": "turn_on"},
            context=scene_ctx,
        )
        await hass.async_block_till_done()

        provenance = tracker.resolve(Context(parent_id=scene_ctx.id))
        assert provenance["cause"]["kind"] == "scene"
    finally:
        tracker.async_stop()


async def test_root_context_is_device_or_integration(hass):
    """A root context with no user and no recorded cause is self-originated."""

    tracker = await _tracker(hass)
    try:
        provenance = tracker.resolve(Context())
        assert provenance["cause"] == {"kind": "device_or_integration"}
    finally:
        tracker.async_stop()


async def test_broken_chain_is_honestly_unknown(hass):
    """A change whose parent was never captured is reported as unknown."""

    tracker = await _tracker(hass)
    try:
        provenance = tracker.resolve(Context(parent_id="never-seen"))
        assert provenance["cause"] == {"kind": "unknown"}
    finally:
        tracker.async_stop()


async def test_resolve_none_context_returns_none(hass):
    """No context to reason about yields no provenance rather than a guess."""

    tracker = await _tracker(hass)
    try:
        assert tracker.resolve(None) is None
    finally:
        tracker.async_stop()


async def test_recent_changes_are_recorded_newest_first(hass):
    """The tracker keeps recent value changes for the causal-chain query."""

    tracker = await _tracker(hass)
    try:
        hass.states.async_set("light.kitchen", "off")
        await hass.async_block_till_done()
        hass.states.async_set("light.kitchen", "on")
        await hass.async_block_till_done()

        changes = tracker.recent_changes("light.kitchen")
        assert changes[0].new_state == "on"
        assert changes[0].old_state == "off"
        # The current state's context resolves through the same tracker.
        current = hass.states.get("light.kitchen")
        assert tracker.resolve(current.context) is not None
    finally:
        tracker.async_stop()


async def test_automation_with_user_propagates_user_id(hass):
    """A user-triggered automation carries the user id into the attribution."""

    tracker = await _tracker(hass)
    try:
        automation_ctx = Context(user_id="user-7")
        hass.bus.async_fire(
            "automation_triggered",
            {"entity_id": "automation.evening", "name": "Evening"},
            context=automation_ctx,
        )
        await hass.async_block_till_done()

        provenance = tracker.resolve(Context(parent_id=automation_ctx.id))
        assert provenance["cause"]["kind"] == "automation"
        assert provenance["userId"] == "user-7"
    finally:
        tracker.async_stop()
