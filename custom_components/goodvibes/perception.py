"""Perception triggers: start an attributed daemon session on a state change.

When enabled in the options flow, the integration watches the state of a chosen
set of entities. A meaningful state change (the state value itself changing, not
just an attribute) starts an attributed GoodVibes daemon session that carries the
triggering context — which entity changed, its old and new value, and the area —
so the daemon can react to something happening in the home.

Boundaries and safeguards
-------------------------
* Off by default. The feature does nothing until ``perception_enabled`` is turned
  on in the options flow and at least one entity is selected.
* Exposed-entities boundary. Only entities the user has exposed to assistants are
  watched, the same boundary the Home Graph snapshot and Home Assistant's own
  voice agents honor (unless the entry opts into unexposed entities). Exposure is
  re-checked on every change, so un-exposing an entity stops its triggers without
  a reload.
* Admin-gated. Turning the feature on and choosing its entities happens in the
  options flow, which Home Assistant restricts to administrators. The session is
  started through the same daemon run-agent path the admin-gated ``run_agent``
  service uses.
* Rate limited. A per-entity minimum interval keeps a chattering entity from
  spawning a flood of sessions.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.const import MATCH_ALL
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event

from .client import GoodVibesClientError
from .const import (
    DEFAULT_PERCEPTION_CONVERSATION_PREFIX,
    DEFAULT_PERCEPTION_DISPLAY_NAME,
    DEFAULT_PERCEPTION_PROMPT,
    PERCEPTION_MIN_INTERVAL_S,
)
from .data import GoodVibesRuntimeData
from .home_graph import _should_include_entity

_LOGGER = logging.getLogger(__name__)

# State values that are not a real observation to act on.
_IGNORED_STATES = {"unknown", "unavailable"}


class GoodVibesPerceptionManager:
    """Watch selected entities and start attributed daemon sessions on change."""

    def __init__(
        self,
        hass: HomeAssistant,
        runtime: GoodVibesRuntimeData,
        entity_ids: list[str],
        prompt: str | None = None,
        *,
        min_interval_s: float = PERCEPTION_MIN_INTERVAL_S,
    ) -> None:
        """Store the watched entities and the attribution instruction."""

        self._hass = hass
        self._runtime = runtime
        self._entity_ids = list(dict.fromkeys(entity_ids))
        self._prompt = (prompt or DEFAULT_PERCEPTION_PROMPT).strip()
        self._min_interval_s = min_interval_s
        self._unsubscribe: Any | None = None
        self._last_fired: dict[str, float] = {}

    @callback
    def async_start(self) -> None:
        """Subscribe to state changes of the watched, exposed entities."""

        watched = [
            entity_id
            for entity_id in self._entity_ids
            if _should_include_entity(
                self._hass, entity_id, self._runtime.include_unexposed_entities
            )
        ]
        if not watched:
            _LOGGER.debug(
                "GoodVibes perception: no exposed entities to watch; not started"
            )
            return
        self._unsubscribe = async_track_state_change_event(
            self._hass, watched, self._async_state_changed
        )
        _LOGGER.debug(
            "GoodVibes perception watching %d entit%s",
            len(watched),
            "y" if len(watched) == 1 else "ies",
        )

    @callback
    def async_stop(self) -> None:
        """Unsubscribe from state-change events."""

        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    @callback
    def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Queue an attributed daemon session for a meaningful state change."""

        entity_id = event.data["entity_id"]
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        # Only real value changes are observations; ignore attribute-only updates
        # and transitions into/out of unknown/unavailable.
        old_value = old_state.state if old_state else None
        new_value = new_state.state
        if old_value == new_value:
            return
        if new_value in _IGNORED_STATES:
            return
        # Re-check exposure so un-exposing an entity stops its triggers live.
        if not _should_include_entity(
            self._hass, entity_id, self._runtime.include_unexposed_entities
        ):
            return
        now = time.monotonic()
        last = self._last_fired.get(entity_id)
        if last is not None and (now - last) < self._min_interval_s:
            return
        self._last_fired[entity_id] = now

        payload = self._build_payload(entity_id, old_value, new_value, new_state)
        self._runtime.entry.async_create_background_task(
            self._hass,
            self._async_start_session(entity_id, payload),
            name=f"goodvibes_perception_{entity_id}",
        )

    def _build_payload(
        self,
        entity_id: str,
        old_value: str | None,
        new_value: str,
        new_state: Any,
    ) -> dict[str, Any]:
        """Build the attributed daemon run-agent payload for a state change."""

        friendly_name = new_state.attributes.get("friendly_name") or entity_id
        area_id = self._resolve_area_id(entity_id)
        changed_at = getattr(new_state, "last_changed", None)
        changed_iso = changed_at.isoformat() if changed_at is not None else None

        task = (
            f"Entity {entity_id} ({friendly_name}) changed from "
            f"'{old_value if old_value is not None else 'unknown'}' to "
            f"'{new_value}'"
        )
        if area_id:
            task += f" in area {area_id}"
        task += f". {self._prompt}"

        context: dict[str, Any] = {
            "trigger": "homeassistant_state_change",
            "entityId": entity_id,
            "friendlyName": friendly_name,
            "oldState": old_value,
            "newState": new_value,
            "source": "goodvibes-perception",
        }
        if area_id:
            context["areaId"] = area_id
        if changed_iso:
            context["changedAt"] = changed_iso

        payload: dict[str, Any] = {
            "task": task,
            "conversationId": (
                f"{DEFAULT_PERCEPTION_CONVERSATION_PREFIX}-{entity_id}"
            ),
            "displayName": DEFAULT_PERCEPTION_DISPLAY_NAME,
            "entityId": entity_id,
            "context": context,
        }
        if area_id:
            payload["areaId"] = area_id
        return payload

    def _resolve_area_id(self, entity_id: str) -> str | None:
        """Resolve an entity's area, directly or through its device."""

        entity_registry = er.async_get(self._hass)
        entry = entity_registry.async_get(entity_id)
        if entry is None:
            return None
        if entry.area_id:
            return entry.area_id
        if entry.device_id:
            device = dr.async_get(self._hass).async_get(entry.device_id)
            if device and device.area_id:
                return device.area_id
        return None

    async def _async_start_session(
        self, entity_id: str, payload: dict[str, Any]
    ) -> None:
        """Start the attributed daemon session and record it on the runtime."""

        try:
            response = await self._runtime.client.run_agent(payload)
        except GoodVibesClientError as err:
            _LOGGER.warning(
                "GoodVibes perception session for %s failed: %s", entity_id, err
            )
            self._runtime.last_error = str(err)
            return
        self._runtime.async_apply_submission_response(response)


def perception_entity_ids(options: dict[str, Any]) -> list[str]:
    """Return the configured perception entity ids from an options mapping."""

    raw = options.get("perception_entities") or []
    if isinstance(raw, str):
        raw = [raw]
    result: list[str] = []
    for value in raw:
        text = str(value).strip()
        if text and text != MATCH_ALL and text not in result:
            result.append(text)
    return result
