"""Causal provenance: why a tracked Home Assistant state changed.

Home Assistant threads a *context* through everything it does. Every state
change, service call, automation run, and script run carries a
:class:`homeassistant.core.Context` with an ``id``, an optional ``parent_id``
that links an effect to the thing that caused it, and an optional ``user_id``
when a person is behind it. Home Assistant's own logbook uses exactly this chain
to attribute events to their cause.

This module builds a small, bounded, in-memory index of that chain so the
integration can answer "why did the light turn on at 3am":

* It listens for the bus events whose context *identifies a cause* — an
  automation run (``automation_triggered``), a script run (``script_started``),
  and a service call (``call_service``) — and records, keyed by that context's
  id, what the cause was.
* Given the context that rode with a state change, :meth:`resolve` walks back up
  the ``parent_id`` chain through that index and attributes the change to the
  nearest automation, script, scene, service call, or user it can reach.

What the context chain genuinely provides vs. what is unknowable
----------------------------------------------------------------
* A state change whose context has a ``user_id`` is genuinely attributable to
  that user.
* A state change reached from a recorded automation/script/scene/service-call
  context is genuinely attributable to it, chained where Home Assistant supplies
  parent contexts.
* A *root* context (no parent, no user, not itself a recorded cause) means the
  change originated from the entity/integration itself — a device report or a
  poll. We report that as ``device_or_integration``. Home Assistant does not
  record *which* integration in the context, so we do not invent one.
* A change whose parent context we never captured (for example, it happened
  before Home Assistant started, or came from a cause this tracker does not
  observe) is reported as ``unknown`` — the chain is broken and guessing would
  be dishonest.

The indexes are recent-history caches bounded by count, not a full audit log.
"""

from __future__ import annotations

import logging
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.const import EVENT_CALL_SERVICE, EVENT_STATE_CHANGED
from homeassistant.core import Context, Event, HomeAssistant, State, callback

from .const import (
    EVENT_AUTOMATION_TRIGGERED,
    EVENT_SCRIPT_STARTED,
    PROVENANCE_CHAIN_MAX_DEPTH,
    PROVENANCE_MAX_CAUSES,
    PROVENANCE_MAX_CHANGES,
    PROVENANCE_MAX_CHANGES_PER_ENTITY,
)

_LOGGER = logging.getLogger(__name__)

# State values that are not a real observation to attribute a cause for.
_IGNORED_STATES = {"unknown", "unavailable"}


@dataclass(frozen=True)
class CauseRecord:
    """One recorded cause: an automation/script/scene run, or a service call."""

    kind: str
    context_id: str
    parent_id: str | None
    user_id: str | None
    entity_id: str | None = None
    name: str | None = None
    domain: str | None = None
    service: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a compact, JSON-safe view of this cause."""

        data: dict[str, Any] = {"kind": self.kind}
        for key, value in (
            ("entityId", self.entity_id),
            ("name", self.name),
            ("domain", self.domain),
            ("service", self.service),
            ("userId", self.user_id),
            ("contextId", self.context_id),
            ("parentId", self.parent_id),
        ):
            if value:
                data[key] = value
        return data


@dataclass(frozen=True)
class ChangeRecord:
    """One observed state change kept for the causal-chain query."""

    entity_id: str
    old_state: str | None
    new_state: str | None
    changed_at: str | None
    context: Context


class GoodVibesProvenanceTracker:
    """Bounded in-memory index of the Home Assistant causal context chain.

    Started once per config entry. It subscribes to the cause-bearing bus events
    and to state changes, keeping both a context-id -> cause map and a small ring
    of recent state changes so :meth:`resolve` and :meth:`recent_changes` can
    attribute a state change to what caused it.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        max_causes: int = PROVENANCE_MAX_CAUSES,
        max_changes: int = PROVENANCE_MAX_CHANGES,
        max_changes_per_entity: int = PROVENANCE_MAX_CHANGES_PER_ENTITY,
    ) -> None:
        """Store the bounds; subscriptions are wired in :meth:`async_start`."""

        self._hass = hass
        self._max_causes = max_causes
        self._max_changes_per_entity = max_changes_per_entity
        self._causes: OrderedDict[str, CauseRecord] = OrderedDict()
        self._changes: dict[str, deque[ChangeRecord]] = {}
        self._change_order: deque[str] = deque()
        self._max_changes = max_changes
        self._unsubscribes: list[Callable[[], None]] = []

    @callback
    def async_start(self) -> None:
        """Subscribe to the cause-bearing bus events and to state changes."""

        bus = self._hass.bus
        self._unsubscribes = [
            bus.async_listen(EVENT_AUTOMATION_TRIGGERED, self._async_record_automation),
            bus.async_listen(EVENT_SCRIPT_STARTED, self._async_record_script),
            bus.async_listen(EVENT_CALL_SERVICE, self._async_record_service_call),
            # All-entity state tracking must go through the raw bus event;
            # async_track_state_change_event indexes by entity id and does not
            # accept a wildcard.
            bus.async_listen(EVENT_STATE_CHANGED, self._async_record_change),
        ]

    @callback
    def async_stop(self) -> None:
        """Unsubscribe from every bus listener and drop the indexes."""

        while self._unsubscribes:
            self._unsubscribes.pop()()
        self._causes.clear()
        self._changes.clear()
        self._change_order.clear()

    # --- recording ----------------------------------------------------------

    @callback
    def _remember_cause(self, record: CauseRecord) -> None:
        """Insert a cause record, evicting the oldest when over the bound."""

        if not record.context_id:
            return
        self._causes[record.context_id] = record
        self._causes.move_to_end(record.context_id)
        while len(self._causes) > self._max_causes:
            self._causes.popitem(last=False)

    @callback
    def _async_record_automation(self, event: Event) -> None:
        self._remember_cause(
            CauseRecord(
                kind="automation",
                context_id=event.context.id,
                parent_id=event.context.parent_id,
                user_id=event.context.user_id,
                entity_id=event.data.get("entity_id"),
                name=event.data.get("name"),
            )
        )

    @callback
    def _async_record_script(self, event: Event) -> None:
        self._remember_cause(
            CauseRecord(
                kind="script",
                context_id=event.context.id,
                parent_id=event.context.parent_id,
                user_id=event.context.user_id,
                entity_id=event.data.get("entity_id"),
                name=event.data.get("name"),
            )
        )

    @callback
    def _async_record_service_call(self, event: Event) -> None:
        domain = event.data.get("domain")
        service = event.data.get("service")
        # A scene being applied is a service call (scene.turn_on); label it as a
        # scene so the attributed cause reads naturally.
        kind = "scene" if domain == "scene" else "service_call"
        self._remember_cause(
            CauseRecord(
                kind=kind,
                context_id=event.context.id,
                parent_id=event.context.parent_id,
                user_id=event.context.user_id,
                domain=domain,
                service=service,
            )
        )

    @callback
    def _async_record_change(self, event: Event) -> None:
        """Keep a small ring of recent value changes for the chain query."""

        new_state: State | None = event.data.get("new_state")
        old_state: State | None = event.data.get("old_state")
        if new_state is None:
            return
        old_value = old_state.state if old_state else None
        new_value = new_state.state
        if old_value == new_value or new_value in _IGNORED_STATES:
            return
        entity_id = new_state.entity_id
        record = ChangeRecord(
            entity_id=entity_id,
            old_state=old_value,
            new_state=new_value,
            changed_at=_iso(getattr(new_state, "last_changed", None)),
            context=new_state.context,
        )
        entity_changes = self._changes.get(entity_id)
        if entity_changes is None:
            entity_changes = deque(maxlen=self._max_changes_per_entity)
            self._changes[entity_id] = entity_changes
        entity_changes.appendleft(record)
        self._change_order.appendleft(entity_id)
        self._prune_changes()

    @callback
    def _prune_changes(self) -> None:
        """Bound the total number of retained changes across all entities."""

        while len(self._change_order) > self._max_changes:
            entity_id = self._change_order.pop()
            entity_changes = self._changes.get(entity_id)
            if entity_changes:
                entity_changes.pop()
                if not entity_changes:
                    self._changes.pop(entity_id, None)

    # --- querying -----------------------------------------------------------

    def recent_changes(self, entity_id: str, limit: int = 10) -> list[ChangeRecord]:
        """Return the most recent retained value changes for an entity."""

        entity_changes = self._changes.get(entity_id)
        if not entity_changes:
            return []
        limit = max(1, int(limit))
        return list(entity_changes)[:limit]

    def resolve(self, context: Context | None) -> dict[str, Any] | None:
        """Attribute a state change to its cause by walking the context chain.

        Returns a JSON-safe provenance dict, or ``None`` when there is no context
        to reason about at all.
        """

        if context is None or not getattr(context, "id", None):
            return None

        user_id = context.user_id
        chain: list[CauseRecord] = []
        seen: set[str] = set()
        node_id: str | None = context.id
        fallback_parent: str | None = context.parent_id

        while node_id and node_id not in seen and len(chain) < PROVENANCE_CHAIN_MAX_DEPTH:
            seen.add(node_id)
            record = self._causes.get(node_id)
            if record is not None:
                chain.append(record)
                if record.user_id and not user_id:
                    user_id = record.user_id
                node_id = record.parent_id
                fallback_parent = None
            elif fallback_parent:
                node_id = fallback_parent
                fallback_parent = None
            else:
                break

        cause = self._primary_cause(chain, context, user_id)
        provenance: dict[str, Any] = {
            "contextId": context.id,
            "cause": cause,
        }
        if context.parent_id:
            provenance["parentId"] = context.parent_id
        if user_id:
            provenance["userId"] = user_id
        if chain:
            provenance["chain"] = [record.as_dict() for record in chain]
        return provenance

    def _primary_cause(
        self,
        chain: list[CauseRecord],
        context: Context,
        user_id: str | None,
    ) -> dict[str, Any]:
        """Choose the most meaningful attributed cause from a walked chain."""

        for kind in ("automation", "script", "scene"):
            for record in chain:
                if record.kind == kind:
                    return record.as_dict()
        for record in chain:
            if record.kind == "service_call":
                return record.as_dict()
        if user_id:
            return {"kind": "user", "userId": user_id}
        # A root context with no parent and no recorded cause originated from the
        # entity/integration itself (a device report or poll). A context whose
        # parent we never captured is honestly unknown.
        if not context.parent_id:
            return {"kind": "device_or_integration"}
        return {"kind": "unknown"}


def _iso(value: Any) -> str | None:
    """Return an ISO-8601 string for a datetime-like value, else ``None``."""

    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)
