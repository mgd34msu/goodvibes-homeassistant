"""Calendar entity for the GoodVibes integration.

Backed entirely by the daemon's ``calendar.events.*`` routes. The daemon owns
the calendar account and its credentials; this entity only asks it and renders
the answer, so the events show up in Home Assistant's calendar UI and are
usable from automations like any other calendar.

When the daemon cannot serve the calendar the entity goes unavailable and says
which of the three reasons applies (see ``mail_calendar``), rather than
presenting an empty calendar as though there were simply no events.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .client import GoodVibesClientError
from .const import CALENDAR_EVENT_MAX_LIMIT, DOMAIN
from .data import GoodVibesRuntimeData
from .mail_calendar import event_payload, event_window, normalize_events

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the GoodVibes calendar entity."""

    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GoodVibesCalendarEntity(runtime)])


def _to_calendar_event(event: dict[str, Any]) -> CalendarEvent | None:
    """Convert one daemon event into a Home Assistant calendar event.

    An event the daemon returns without a usable start/end pair is skipped
    rather than shown with an invented time.
    """

    window = event_window(event)
    if window is None:
        return None
    start, end = window
    summary = event.get("title") or event.get("summary") or "(no title)"
    kwargs: dict[str, Any] = {"start": start, "end": end, "summary": str(summary)}
    for source, target in (
        ("description", "description"),
        ("location", "location"),
        ("uid", "uid"),
        ("id", "uid"),
    ):
        value = event.get(source)
        if value not in (None, "") and not kwargs.get(target):
            kwargs[target] = str(value)
    return CalendarEvent(**kwargs)


class GoodVibesCalendarEntity(CalendarEntity):
    """The daemon's calendar, presented as a Home Assistant calendar."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "calendar"
    _attr_icon = "mdi:calendar-account"
    _attr_supported_features = CalendarEntityFeature.CREATE_EVENT

    def __init__(self, runtime: GoodVibesRuntimeData) -> None:
        """Initialize the calendar entity."""

        self._runtime = runtime
        base_unique_id = runtime.entry.unique_id or runtime.entry.entry_id
        self._attr_unique_id = f"{base_unique_id}_calendar"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry metadata."""

        return {
            "identifiers": {(DOMAIN, self._runtime.device_identifier)},
            "manufacturer": "GoodVibes",
            "model": self._runtime.device_model,
            "name": self._runtime.device_name,
            "sw_version": self._runtime.sw_version,
        }

    @property
    def available(self) -> bool:
        """Report unavailable unless the daemon can actually serve the calendar.

        Showing an empty calendar when the daemon has no calendar account
        connected, or does not serve the routes at all, would look like "you
        have no events" instead of "this is not set up". The reason is on the
        GoodVibes mail and calendar sensor and in the error raised by any
        attempted call.
        """

        return self._runtime.daemon_connected and self._runtime.mail_calendar.ready

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose why the calendar is in its current state."""

        state = self._runtime.mail_calendar
        attrs: dict[str, Any] = {"status": state.state}
        if state.next_step:
            attrs["next_step"] = state.next_step
        return attrs

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event.

        Read from the events the last refresh already fetched, so the entity
        state does not trigger its own daemon round-trip.
        """

        now = dt_util.now()
        upcoming: list[CalendarEvent] = []
        for raw in self._runtime.mail_calendar.events:
            converted = _to_calendar_event(dict(raw))
            if converted is None:
                continue
            end = converted.end
            end_dt = (
                end
                if isinstance(end, datetime)
                else dt_util.start_of_local_day(end)
            )
            if end_dt >= now:
                upcoming.append(converted)
        if not upcoming:
            return None
        return min(
            upcoming,
            key=lambda item: (
                item.start
                if isinstance(item.start, datetime)
                else dt_util.start_of_local_day(item.start)
            ),
        )

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return the daemon's events in a window, for the calendar UI."""

        payload = {
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
            "limit": CALENDAR_EVENT_MAX_LIMIT,
        }
        try:
            response = await self._runtime.client.calendar_events_list(payload)
        except GoodVibesClientError as err:
            self._runtime.async_apply_mail_calendar_error(err)
            raise HomeAssistantError(
                self._runtime.mail_calendar.error_message("read the calendar")
            ) from err

        events: list[CalendarEvent] = []
        for raw in normalize_events(response):
            converted = _to_calendar_event(dict(raw))
            if converted is not None:
                events.append(converted)
        return events

    async def async_create_event(self, **kwargs: Any) -> None:
        """Create an event on the daemon's calendar."""

        payload = event_payload(kwargs)
        if not payload.get("title"):
            raise HomeAssistantError("A calendar event needs a summary.")
        if not payload.get("start") or not payload.get("end"):
            raise HomeAssistantError("A calendar event needs a start and an end.")
        try:
            await self._runtime.client.calendar_event_create(payload)
        except GoodVibesClientError as err:
            self._runtime.async_apply_mail_calendar_error(err)
            raise HomeAssistantError(
                self._runtime.mail_calendar.error_message("create the event")
            ) from err
        await self._runtime.async_refresh_mail_calendar()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to runtime updates."""

        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._runtime.signal, self.async_write_ha_state
            )
        )
