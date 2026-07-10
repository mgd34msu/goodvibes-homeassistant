"""Consent-gated habit mining: recurring-pattern PROPOSALS, never silent rules.

When the user opts in (off by default, enabled through the admin-only options
flow), the integration keeps a bounded, in-memory record of its *own* observed
state changes and periodically runs a local frequency analysis over that record.
Recurring patterns — "this controllable entity tends to change to this state at
about this time on weekdays" — are surfaced as automation **proposals** for the
user to review. Nothing is ever created silently, and no observation data leaves
the machine.

Honesty and boundaries
----------------------
* Off by default; the analysis only runs while ``habit_mining_enabled`` is set.
* In-memory only. Observations are held in a bounded buffer capped by both age
  (the configured retention days) and count. They are not written to disk and do
  not survive a restart, so proposals reflect only the retained window. This is
  stated plainly rather than pretending to mine a long history.
* Proposals only. A proposal carries a ready-to-use standard Home Assistant
  automation config, but it is created only when the user explicitly accepts it
  (the ``accept_habit`` service, admin-gated, requiring confirmation).
* Actionable only. A proposal is generated only for an entity whose observed
  state maps to a safe, well-understood Home Assistant service (turn on/off,
  open/close, lock/unlock…). Anything else is not turned into a control
  automation.
"""

from __future__ import annotations

import hashlib
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    HABIT_ANALYSIS_INTERVAL_MINUTES,
    HABIT_MAX_OBSERVATIONS,
    HABIT_MIN_DISTINCT_DAYS,
    HABIT_MIN_OCCURRENCES,
    HABIT_TIME_BUCKET_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

_IGNORED_STATES = {"unknown", "unavailable", ""}

_WEEKDAY_DAYS = ["mon", "tue", "wed", "thu", "fri"]
_WEEKEND_DAYS = ["sat", "sun"]


# Map an observed (domain, state) to a safe Home Assistant service that
# reproduces it. Only entities whose change maps here become control proposals.
def state_to_service(entity_id: str, state: str) -> tuple[str, str] | None:
    """Return ``(service_domain, service)`` reproducing a state, or ``None``.

    Only well-understood, safe reproductions are mapped. The service domain is
    returned separately from the entity domain because, for example, a
    ``cover`` open maps to the ``cover.open_cover`` service.
    """

    domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    value = (state or "").lower()
    on_off = {
        "light",
        "switch",
        "fan",
        "input_boolean",
        "humidifier",
        "siren",
    }
    if domain in on_off:
        if value == "on":
            return (domain, "turn_on")
        if value == "off":
            return (domain, "turn_off")
        return None
    if domain == "cover":
        if value == "open":
            return ("cover", "open_cover")
        if value == "closed":
            return ("cover", "close_cover")
        return None
    if domain == "lock":
        if value == "locked":
            return ("lock", "lock")
        if value == "unlocked":
            return ("lock", "unlock")
        return None
    return None


@dataclass(frozen=True)
class Observation:
    """One observed value change kept for local analysis."""

    entity_id: str
    state: str
    when: datetime


@dataclass
class HabitProposal:
    """A recurring pattern surfaced for the user to review, never auto-created."""

    proposal_id: str
    entity_id: str
    state: str
    day_type: str
    time: str
    occurrences: int
    distinct_days: int
    first_seen: str
    last_seen: str
    friendly_name: str | None = None

    @property
    def weekdays(self) -> list[str]:
        """Return the automation weekday condition for this pattern's day type."""

        return _WEEKDAY_DAYS if self.day_type == "weekday" else _WEEKEND_DAYS

    def description(self) -> str:
        """Return a plain-language description of the observed pattern."""

        name = self.friendly_name or self.entity_id
        day_phrase = "on weekdays" if self.day_type == "weekday" else "on weekends"
        return (
            f"{name} changed to '{self.state}' around {self.time} {day_phrase} "
            f"on {self.distinct_days} day(s) ({self.occurrences} times observed)."
        )

    def automation_config(self) -> dict[str, Any] | None:
        """Return a standard Home Assistant automation config for this pattern.

        Returns ``None`` when the observed change has no safe service mapping, so
        callers refuse to synthesize a control action they cannot make honestly.
        """

        mapping = state_to_service(self.entity_id, self.state)
        if mapping is None:
            return None
        service_domain, service = mapping
        name = self.friendly_name or self.entity_id
        day_phrase = "weekdays" if self.day_type == "weekday" else "weekends"
        return {
            "id": f"goodvibes_habit_{self.proposal_id}",
            "alias": f"GoodVibes habit: {name} {service} at {self.time} on {day_phrase}",
            "description": (
                "Proposed by GoodVibes habit mining from locally observed "
                "history. Review and adjust before relying on it."
            ),
            "trigger": [{"platform": "time", "at": f"{self.time}:00"}],
            "condition": [{"condition": "time", "weekday": self.weekdays}],
            "action": [
                {
                    "service": f"{service_domain}.{service}",
                    "target": {"entity_id": self.entity_id},
                }
            ],
            "mode": "single",
        }

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe view, including the proposed automation config."""

        return {
            "proposalId": self.proposal_id,
            "entityId": self.entity_id,
            "state": self.state,
            "dayType": self.day_type,
            "time": self.time,
            "occurrences": self.occurrences,
            "distinctDays": self.distinct_days,
            "firstSeen": self.first_seen,
            "lastSeen": self.last_seen,
            "friendlyName": self.friendly_name,
            "description": self.description(),
            "automation": self.automation_config(),
        }


def _day_type(moment: datetime) -> str:
    return "weekday" if moment.weekday() < 5 else "weekend"


def detect_habits(
    observations: list[Observation],
    *,
    min_distinct_days: int = HABIT_MIN_DISTINCT_DAYS,
    min_occurrences: int = HABIT_MIN_OCCURRENCES,
    bucket_minutes: int = HABIT_TIME_BUCKET_MINUTES,
    friendly_names: dict[str, str] | None = None,
) -> list[HabitProposal]:
    """Detect recurring (entity, state, day-type, time-of-day) patterns.

    A pattern is proposed only when it recurs on at least ``min_distinct_days``
    distinct calendar days and at least ``min_occurrences`` times overall, and
    only for entities whose state maps to a safe reproducing service. The
    detection is a pure function so it can be tested without Home Assistant.
    """

    friendly_names = friendly_names or {}
    bucket_minutes = max(1, int(bucket_minutes))
    groups: dict[tuple[str, str, str, int], list[datetime]] = {}
    for obs in observations:
        if state_to_service(obs.entity_id, obs.state) is None:
            continue
        minutes_of_day = obs.when.hour * 60 + obs.when.minute
        bucket = minutes_of_day // bucket_minutes
        key = (obs.entity_id, obs.state, _day_type(obs.when), bucket)
        groups.setdefault(key, []).append(obs.when)

    proposals: list[HabitProposal] = []
    for (entity_id, state, day_type, _bucket), moments in groups.items():
        distinct_days = len({moment.date() for moment in moments})
        occurrences = len(moments)
        if distinct_days < min_distinct_days or occurrences < min_occurrences:
            continue
        avg_minutes = round(
            sum(moment.hour * 60 + moment.minute for moment in moments) / occurrences
        )
        avg_minutes = max(0, min(24 * 60 - 1, avg_minutes))
        time_str = f"{avg_minutes // 60:02d}:{avg_minutes % 60:02d}"
        ordered = sorted(moments)
        digest = hashlib.sha1(
            f"{entity_id}|{state}|{day_type}|{time_str}".encode()
        ).hexdigest()[:12]
        proposals.append(
            HabitProposal(
                proposal_id=digest,
                entity_id=entity_id,
                state=state,
                day_type=day_type,
                time=time_str,
                occurrences=occurrences,
                distinct_days=distinct_days,
                first_seen=ordered[0].isoformat(),
                last_seen=ordered[-1].isoformat(),
                friendly_name=friendly_names.get(entity_id),
            )
        )
    # Deterministic, stable ordering: strongest signal first.
    proposals.sort(key=lambda p: (-p.distinct_days, -p.occurrences, p.entity_id))
    return proposals


class HabitObservationStore:
    """Bounded, in-memory buffer of observed value changes for one entry.

    Capped by both count (``max_observations``) and age (``retention``): every
    record is pruned once it falls outside the retention window, and the oldest
    are dropped if the count cap is reached first.
    """

    def __init__(self, retention: timedelta, max_observations: int) -> None:
        self._retention = retention
        self._observations: deque[Observation] = deque(maxlen=max_observations)

    def record(self, entity_id: str, state: str, when: datetime) -> None:
        """Append one observation and prune anything past the retention window."""

        self._observations.append(Observation(entity_id, state, when))
        self.prune(when)

    def prune(self, now: datetime) -> None:
        """Drop observations older than the retention window."""

        cutoff = now - self._retention
        while self._observations and self._observations[0].when < cutoff:
            self._observations.popleft()

    def observations(self) -> list[Observation]:
        """Return a snapshot list of the currently retained observations."""

        return list(self._observations)

    def __len__(self) -> int:
        return len(self._observations)


class GoodVibesHabitMiner:
    """Opt-in local habit mining: records observations, proposes automations.

    Watches state changes of exposed, controllable entities, retains them in a
    bounded in-memory store, and periodically runs :func:`detect_habits`. Results
    are handed to ``on_proposals`` (the runtime/services layer) for surfacing.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        runtime: Any,
        *,
        retention_days: int,
        on_proposals,
        analysis_interval_minutes: int = HABIT_ANALYSIS_INTERVAL_MINUTES,
        max_observations: int = HABIT_MAX_OBSERVATIONS,
    ) -> None:
        self._hass = hass
        self._runtime = runtime
        self._on_proposals = on_proposals
        self._analysis_interval = timedelta(minutes=analysis_interval_minutes)
        self.store = HabitObservationStore(
            timedelta(days=retention_days), max_observations
        )
        self._unsub_state = None
        self._unsub_interval = None

    @callback
    def async_start(self) -> None:
        """Subscribe to state changes and schedule the periodic analysis."""

        # All-entity tracking uses the raw bus event; the entity-indexed helper
        # does not accept a wildcard.
        self._unsub_state = self._hass.bus.async_listen(
            EVENT_STATE_CHANGED, self._async_state_changed
        )
        self._unsub_interval = async_track_time_interval(
            self._hass, self._async_scheduled_analysis, self._analysis_interval
        )

    @callback
    def async_stop(self) -> None:
        """Unsubscribe from state changes and cancel the scheduled analysis."""

        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None
        if self._unsub_interval is not None:
            self._unsub_interval()
            self._unsub_interval = None

    @callback
    def _async_state_changed(self, event: Event) -> None:
        """Record an exposed, actionable value change as an observation."""

        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None:
            return
        entity_id = new_state.entity_id
        new_value = new_state.state
        old_value = old_state.state if old_state else None
        if old_value == new_value or new_value in _IGNORED_STATES:
            return
        # Only controllable entities whose state can be reproduced are useful for
        # proposing an automation; skip everything else so the store stays lean.
        if state_to_service(entity_id, new_value) is None:
            return
        # Honor the same exposed-to-assistants boundary the rest of the
        # integration respects, unless the entry opts into unexposed entities.
        if not _should_include(self._hass, self._runtime, entity_id):
            return
        when = getattr(new_state, "last_changed", None) or dt_util.utcnow()
        self.store.record(entity_id, new_value, dt_util.as_local(when))

    async def _async_scheduled_analysis(self, _now: datetime) -> None:
        """Run the analysis on the timer and surface any proposals."""

        proposals = self.analyze()
        await self._on_proposals(proposals)

    def analyze(self) -> list[HabitProposal]:
        """Prune, then detect proposals over the retained observations."""

        now = dt_util.as_local(dt_util.utcnow())
        self.store.prune(now)
        friendly_names = {}
        for obs in self.store.observations():
            state = self._hass.states.get(obs.entity_id)
            if state is not None:
                name = state.attributes.get("friendly_name")
                if name:
                    friendly_names[obs.entity_id] = str(name)
        return detect_habits(
            self.store.observations(), friendly_names=friendly_names
        )


def _should_include(hass: HomeAssistant, runtime: Any, entity_id: str) -> bool:
    """Return whether an entity is in scope for observation."""

    # Imported lazily to avoid a hard import cycle at module load.
    from .home_graph import _should_include_entity

    return _should_include_entity(
        hass, entity_id, getattr(runtime, "include_unexposed_entities", False)
    )


async def async_create_automation_from_config(
    hass: HomeAssistant, config: dict[str, Any]
) -> str:
    """Create a standard Home Assistant automation from a proposal's config.

    The automation is appended to Home Assistant's default UI automation store
    (``automations.yaml``) and the ``automation`` integration is reloaded, which
    is the same path Home Assistant's own automation editor uses. Returns the new
    automation's id. Raises :class:`HomeAssistantError` if an automation with the
    same id already exists (so accepting the same proposal twice is refused).
    """

    from homeassistant.exceptions import HomeAssistantError

    path = hass.config.path("automations.yaml")
    automation_id = str(config.get("id"))

    def _read_and_write() -> None:
        import os

        from homeassistant.util.yaml import load_yaml, save_yaml

        existing: Any = []
        if os.path.exists(path):
            loaded = load_yaml(path)
            if isinstance(loaded, list):
                existing = loaded
            elif loaded:
                existing = [loaded]
        for item in existing:
            if isinstance(item, dict) and str(item.get("id")) == automation_id:
                raise HomeAssistantError(
                    f"An automation with id {automation_id} already exists"
                )
        existing.append(config)
        save_yaml(path, existing)

    await hass.async_add_executor_job(_read_and_write)

    if hass.services.has_service("automation", "reload"):
        await hass.services.async_call("automation", "reload", blocking=True)
    return automation_id
