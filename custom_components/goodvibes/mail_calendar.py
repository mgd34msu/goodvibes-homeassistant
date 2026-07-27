"""Mail and calendar support backed by the GoodVibes daemon.

The daemon owns the mail and calendar accounts and every credential behind
them. This integration holds none: it calls the daemon's ``email.*`` and
``calendar.events.*`` routes and presents the results the way Home Assistant
expects — a calendar entity, services, and a diagnostic sensor.

The whole point of this module is to be honest about *why* mail and calendar
are not working when they are not working, because the three reasons have three
different fixes and are easy to conflate:

* ``unsupported``  — the daemon does not serve the routes here. Either it is
  older than the mail/calendar surface (HTTP 404), or it is current and the
  route is real but no handler is attached in the composition it was built with
  (HTTP 501 ``NOT_INVOKABLE``). Fix: update the daemon, or run one whose
  composition wires mail and calendar.
* ``needs_setup``  — the routes are served, but no mail or calendar account is
  connected on the daemon. Fix: connect one on the daemon host.
* ``unavailable``  — the daemon could not be reached at all. Fix: check that it
  is running and that the URL and token are right.

Every one of those carries the concrete next step with it (see
``const.MAIL_CALENDAR_NEXT_STEPS``), so nothing ever surfaces as a bare
"unavailable" with no explanation and nothing fails silently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from homeassistant.util import dt as dt_util

from .client import (
    GoodVibesClientError,
    GoodVibesSurfaceMissingError,
    GoodVibesUnavailableError,
)
from .const import (
    MAIL_CALENDAR_NEEDS_SETUP,
    MAIL_CALENDAR_NOT_CONFIGURED_CODES,
    MAIL_CALENDAR_NEXT_STEPS,
    MAIL_CALENDAR_NOT_CONFIGURED_HINTS,
    MAIL_CALENDAR_READY,
    MAIL_CALENDAR_UNAVAILABLE,
    MAIL_CALENDAR_UNKNOWN,
    MAIL_CALENDAR_UNSUPPORTED,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class MailCalendarState:
    """What the daemon can currently do for mail and calendar, and why."""

    state: str = MAIL_CALENDAR_UNKNOWN
    #: Raw daemon error behind a non-ready state, for diagnostics.
    detail: str | None = None
    #: When the surface was last probed.
    checked_at: str | None = None
    #: The most recent calendar event list, used by the calendar entity.
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        """Whether mail and calendar calls can be expected to work."""

        return self.state == MAIL_CALENDAR_READY

    @property
    def next_step(self) -> str | None:
        """The concrete action that would fix a non-ready state."""

        return MAIL_CALENDAR_NEXT_STEPS.get(self.state)

    def as_attributes(self) -> dict[str, Any]:
        """Return the diagnostic attributes shown on the status sensor."""

        return {
            "state": self.state,
            "next_step": self.next_step,
            "detail": self.detail,
            "checked_at": self.checked_at,
            "event_count": len(self.events),
        }

    def error_message(self, action: str) -> str:
        """Build the message raised when ``action`` is attempted while not ready."""

        next_step = self.next_step or "Check the GoodVibes daemon."
        return f"Cannot {action}: {next_step}"


def classify_error(err: GoodVibesClientError) -> tuple[str, str]:
    """Map a daemon client error onto a mail/calendar state and its detail.

    The daemon's machine ``code`` decides this whenever there is one. That is
    the contract; the message is prose and has already changed underneath this
    function once. When the daemon began actually serving these routes it
    answered "No Google account is connected on this machine" with
    ``code: CALENDAR_NOT_CONFIGURED``, and the old substring list matched none
    of it — so an unconfigured calendar fell through to the ready default and
    would have reported itself ready with nothing behind it.

    A 404 (or a 501 saying the route is real but unwired here) means the surface
    is not available on this daemon at all. A reachable daemon that answers "no
    account connected" means the surface exists with nothing behind it — a
    different problem with a different fix, so it is not collapsed into the same
    bucket.
    """

    detail = str(err)
    if isinstance(err, GoodVibesUnavailableError):
        return MAIL_CALENDAR_UNAVAILABLE, detail
    if isinstance(err, GoodVibesSurfaceMissingError):
        return MAIL_CALENDAR_UNSUPPORTED, detail
    if err.code and err.code in MAIL_CALENDAR_NOT_CONFIGURED_CODES:
        return MAIL_CALENDAR_NEEDS_SETUP, detail
    lowered = detail.lower()
    # Fallback for a daemon old enough to answer without a machine code.
    if any(hint in lowered for hint in MAIL_CALENDAR_NOT_CONFIGURED_HINTS):
        return MAIL_CALENDAR_NEEDS_SETUP, detail
    # A reachable daemon returning some other error is not evidence that mail
    # and calendar are unusable in general, so the surface is not condemned on
    # it; the error is still reported.
    return MAIL_CALENDAR_READY, detail


async def async_probe(client, *, calendar_id: str | None = None) -> MailCalendarState:
    """Probe the daemon's calendar surface and classify what came back.

    ``calendar.events.list`` is used as the probe because it is read-only, needs
    no arguments, and is refused in exactly the same way by a daemon with no
    account connected as the rest of the surface. Mail and calendar are served
    by the same daemon build and configured together, so one probe covers both.
    """

    checked_at = dt_util.utcnow().isoformat()
    payload: dict[str, Any] = {}
    if calendar_id:
        payload["calendarId"] = calendar_id
    try:
        response = await client.calendar_events_list(payload)
    except GoodVibesClientError as err:
        state, detail = classify_error(err)
        if state == MAIL_CALENDAR_READY:
            # Reachable and served, but this particular read failed.
            _LOGGER.debug("GoodVibes calendar probe returned an error: %s", detail)
        return MailCalendarState(state=state, detail=detail, checked_at=checked_at)

    return MailCalendarState(
        state=MAIL_CALENDAR_READY,
        detail=None,
        checked_at=checked_at,
        events=normalize_events(response),
    )


def normalize_events(response: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Return the event list from a ``calendar.events.list`` response."""

    if not isinstance(response, Mapping):
        return []
    events = response.get("events")
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, Mapping)]


def parse_timestamp(value: Any) -> datetime | date | None:
    """Parse a daemon event timestamp into a datetime, or a date for all-day.

    The daemon serves ISO-8601 strings. A date-only string (``2026-08-01``) is
    an all-day event, which Home Assistant represents as a ``date`` rather than
    a ``datetime``, so the two are kept distinct instead of forcing midnight.
    """

    if isinstance(value, datetime):
        return dt_util.as_local(value) if value.tzinfo else value
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if len(text) == 10 and text.count("-") == 2:
        parsed_date = dt_util.parse_date(text)
        if parsed_date is not None:
            return parsed_date
    parsed = dt_util.parse_datetime(text)
    if parsed is None:
        return None
    # A daemon timestamp without a zone is interpreted in Home Assistant's own
    # timezone rather than silently assumed to be UTC.
    return parsed if parsed.tzinfo else dt_util.as_local(parsed)


def event_window(event: Mapping[str, Any]) -> tuple[Any, Any] | None:
    """Return the (start, end) of a daemon event, or None when unusable.

    An event with a start but no end is given a one-hour default rather than
    being dropped, because Home Assistant requires both and a missing end is a
    formatting gap rather than a reason to hide the event.
    """

    start = parse_timestamp(event.get("start"))
    if start is None:
        return None
    end = parse_timestamp(event.get("end"))
    if end is None:
        if isinstance(start, datetime):
            end = start + timedelta(hours=1)
        else:
            end = start + timedelta(days=1)
    # Home Assistant requires both ends to be the same kind.
    if isinstance(start, datetime) != isinstance(end, datetime):
        return None
    if end < start:
        return None
    return start, end


def event_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    """Build a ``calendar.events.create`` body from Home Assistant service data.

    Home Assistant's field names are snake_case; the daemon contract is
    camelCase. Only fields the user actually supplied are sent, so the daemon's
    own defaults apply to the rest.
    """

    payload: dict[str, Any] = {}
    for ha_key, daemon_key in (
        ("title", "title"),
        ("summary", "title"),
        ("description", "description"),
        ("location", "location"),
        ("calendar_id", "calendarId"),
    ):
        value = data.get(ha_key)
        if value not in (None, "") and daemon_key not in payload:
            payload[daemon_key] = value

    for ha_key, daemon_key in (("start", "start"), ("end", "end")):
        value = data.get(ha_key)
        if value in (None, ""):
            continue
        if isinstance(value, (datetime, date)):
            payload[daemon_key] = value.isoformat()
        else:
            payload[daemon_key] = str(value)

    attendees = data.get("attendees")
    if isinstance(attendees, (list, tuple)) and attendees:
        payload["attendees"] = [str(item) for item in attendees]
    elif isinstance(attendees, str) and attendees.strip():
        payload["attendees"] = [attendees.strip()]

    # The daemon requires explicit confirmation on event creation. A Home
    # Assistant service call or a calendar-entity create IS the explicit user
    # action the flag is asking about, so it is set here rather than being
    # surfaced as a field the user has to remember to tick.
    payload["confirm"] = True
    return payload
