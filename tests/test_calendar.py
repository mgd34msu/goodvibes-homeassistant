"""The GoodVibes calendar entity.

The entity is a view onto the daemon's calendar. The behavior that matters is
that it never pretends: an empty calendar and a calendar that cannot be reached
must look different to the user, because "you have no events today" and "this
was never set up" are not the same statement.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.goodvibes.calendar import (
    GoodVibesCalendarEntity,
    _to_calendar_event,
)
from custom_components.goodvibes.client import (
    GoodVibesDaemonError,
    GoodVibesSurfaceMissingError,
)
from custom_components.goodvibes.const import (
    DOMAIN,
    MAIL_CALENDAR_NEEDS_SETUP,
    MAIL_CALENDAR_UNSUPPORTED,
)
from custom_components.goodvibes.data import GoodVibesRuntimeData
from custom_components.goodvibes.mail_calendar import MailCalendarState

DAEMON = "http://127.0.0.1:3421"
ENTRY_DATA = {
    "daemon_url": DAEMON,
    "daemon_token": "tok",
    "webhook_secret": "secret",
    "event_type": "goodvibes_message",
    "home_graph_enabled": False,
    "installation_id": "inst",
    "knowledge_space_id": "",
}


class _CalendarClient:
    def __init__(self, *, events=None, error=None) -> None:
        self.daemon_url = DAEMON
        self.events = events if events is not None else []
        self.error = error
        self.sent: list[tuple[str, dict]] = []

    async def calendar_events_list(self, payload):
        self.sent.append(("calendar_events_list", dict(payload)))
        if self.error is not None:
            raise self.error
        return {"events": list(self.events)}

    async def calendar_event_create(self, payload):
        self.sent.append(("calendar_event_create", dict(payload)))
        if self.error is not None:
            raise self.error
        return {"id": "evt-1"}


def _entity(hass, client, *, state: MailCalendarState | None = None):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DAEMON, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    runtime = GoodVibesRuntimeData(
        hass=hass,
        entry=entry,
        client=client,
        event_type="goodvibes_message",
        home_graph_enabled=False,
        installation_id="inst",
        knowledge_space_id=None,
    )
    if state is not None:
        runtime.mail_calendar = state
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    return GoodVibesCalendarEntity(runtime), runtime


def _iso(offset_hours: float) -> str:
    return (dt_util.now() + timedelta(hours=offset_hours)).isoformat()


# --------------------------------------------------------------------------
# Availability is honest
# --------------------------------------------------------------------------


def test_calendar_is_unavailable_rather_than_empty_when_not_set_up(hass):
    """An unconfigured calendar must not read as 'no events'."""

    entity, _ = _entity(
        hass,
        _CalendarClient(),
        state=MailCalendarState(state=MAIL_CALENDAR_NEEDS_SETUP),
    )
    assert entity.available is False
    assert entity.extra_state_attributes["status"] == MAIL_CALENDAR_NEEDS_SETUP
    assert "Connect one on the daemon host" in entity.extra_state_attributes["next_step"]


def test_calendar_is_unavailable_when_the_daemon_does_not_serve_the_routes(hass):
    entity, _ = _entity(
        hass,
        _CalendarClient(),
        state=MailCalendarState(state=MAIL_CALENDAR_UNSUPPORTED),
    )
    assert entity.available is False
    assert "Update the daemon" in entity.extra_state_attributes["next_step"]


def test_calendar_is_available_once_the_daemon_serves_it(hass):
    from custom_components.goodvibes.const import MAIL_CALENDAR_READY

    entity, _ = _entity(
        hass, _CalendarClient(), state=MailCalendarState(state=MAIL_CALENDAR_READY)
    )
    assert entity.available is True


def test_calendar_is_unavailable_while_the_daemon_connection_is_down(hass):
    from custom_components.goodvibes.const import MAIL_CALENDAR_READY

    entity, runtime = _entity(
        hass, _CalendarClient(), state=MailCalendarState(state=MAIL_CALENDAR_READY)
    )
    runtime.daemon_connected = False
    assert entity.available is False


# --------------------------------------------------------------------------
# Event rendering
# --------------------------------------------------------------------------


def test_a_daemon_event_becomes_a_home_assistant_event():
    converted = _to_calendar_event(
        {
            "id": "evt-1",
            "title": "Standup",
            "description": "Daily",
            "location": "Office",
            "start": "2026-08-01T09:00:00+00:00",
            "end": "2026-08-01T09:15:00+00:00",
        }
    )
    assert converted is not None
    assert converted.summary == "Standup"
    assert converted.description == "Daily"
    assert converted.location == "Office"
    assert converted.uid == "evt-1"


def test_an_event_with_an_unusable_time_is_skipped_not_invented():
    assert _to_calendar_event({"title": "Broken", "start": "nonsense"}) is None


def test_an_untitled_event_is_still_shown():
    converted = _to_calendar_event(
        {"start": "2026-08-01T09:00:00+00:00", "end": "2026-08-01T10:00:00+00:00"}
    )
    assert converted is not None
    assert converted.summary == "(no title)"


def test_event_property_returns_the_next_upcoming_event(hass):
    from custom_components.goodvibes.const import MAIL_CALENDAR_READY

    state = MailCalendarState(
        state=MAIL_CALENDAR_READY,
        events=[
            {"id": "past", "title": "Over", "start": _iso(-5), "end": _iso(-4)},
            {"id": "later", "title": "Later", "start": _iso(6), "end": _iso(7)},
            {"id": "soon", "title": "Soon", "start": _iso(2), "end": _iso(3)},
        ],
    )
    entity, _ = _entity(hass, _CalendarClient(), state=state)
    assert entity.event is not None
    assert entity.event.summary == "Soon"


def test_event_property_is_none_when_everything_is_in_the_past(hass):
    from custom_components.goodvibes.const import MAIL_CALENDAR_READY

    state = MailCalendarState(
        state=MAIL_CALENDAR_READY,
        events=[{"id": "past", "title": "Over", "start": _iso(-5), "end": _iso(-4)}],
    )
    entity, _ = _entity(hass, _CalendarClient(), state=state)
    assert entity.event is None


# --------------------------------------------------------------------------
# Reads and writes go to the daemon
# --------------------------------------------------------------------------


async def test_get_events_asks_the_daemon_for_the_window(hass):
    client = _CalendarClient(
        events=[
            {
                "id": "1",
                "title": "Standup",
                "start": "2026-08-01T09:00:00+00:00",
                "end": "2026-08-01T09:15:00+00:00",
            }
        ]
    )
    entity, _ = _entity(hass, client)
    start = datetime(2026, 8, 1, tzinfo=dt_util.UTC)
    end = datetime(2026, 8, 31, tzinfo=dt_util.UTC)
    events = await entity.async_get_events(hass, start, end)
    assert len(events) == 1
    _, payload = client.sent[-1]
    assert payload["from"] == start.isoformat()
    assert payload["to"] == end.isoformat()


async def test_get_events_reports_the_reason_when_the_daemon_refuses(hass):
    client = _CalendarClient(
        error=GoodVibesSurfaceMissingError("HTTP 404: Route not found", status=404)
    )
    entity, runtime = _entity(hass, client)
    with pytest.raises(HomeAssistantError) as err:
        await entity.async_get_events(
            hass,
            datetime(2026, 8, 1, tzinfo=dt_util.UTC),
            datetime(2026, 8, 2, tzinfo=dt_util.UTC),
        )
    assert "Update the daemon" in str(err.value)
    assert runtime.mail_calendar.state == MAIL_CALENDAR_UNSUPPORTED


async def test_create_event_sends_the_daemon_contract_shape(hass):
    client = _CalendarClient()
    entity, _ = _entity(hass, client)
    entity.hass = hass
    entity.entity_id = "calendar.goodvibes"
    # The entity is built directly here rather than through a platform, so the
    # state write it would normally do is stubbed out.
    with patch.object(GoodVibesCalendarEntity, "async_write_ha_state"):
        await entity.async_create_event(
            summary="Dentist",
            start=datetime(2026, 8, 1, 9, 0, tzinfo=dt_util.UTC),
            end=datetime(2026, 8, 1, 10, 0, tzinfo=dt_util.UTC),
        )
    name, payload = client.sent[0]
    assert name == "calendar_event_create"
    assert payload["title"] == "Dentist"
    assert payload["confirm"] is True


async def test_create_event_reports_the_reason_when_no_account_is_connected(hass):
    client = _CalendarClient(
        error=GoodVibesDaemonError(
            "HTTP 400: calendar account is not configured", status=400
        )
    )
    entity, runtime = _entity(hass, client)
    entity.hass = hass
    entity.entity_id = "calendar.goodvibes"
    with pytest.raises(HomeAssistantError) as err:
        await entity.async_create_event(
            summary="Dentist",
            start=datetime(2026, 8, 1, 9, 0, tzinfo=dt_util.UTC),
            end=datetime(2026, 8, 1, 10, 0, tzinfo=dt_util.UTC),
        )
    assert "Connect one on the daemon host" in str(err.value)
    assert runtime.mail_calendar.state == MAIL_CALENDAR_NEEDS_SETUP


async def test_create_event_rejects_an_event_with_no_times(hass):
    entity, _ = _entity(hass, _CalendarClient())
    entity.hass = hass
    with pytest.raises(HomeAssistantError):
        await entity.async_create_event(summary="No times")


# --------------------------------------------------------------------------
# Platform wiring
# --------------------------------------------------------------------------


async def test_the_calendar_platform_adds_one_entity(hass):
    """The platform entry point is wired up the way Home Assistant expects."""

    from custom_components.goodvibes.calendar import async_setup_entry

    entry = MockConfigEntry(domain=DOMAIN, unique_id=DAEMON, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    runtime = GoodVibesRuntimeData(
        hass=hass,
        entry=entry,
        client=_CalendarClient(),
        event_type="goodvibes_message",
        home_graph_enabled=False,
        installation_id="inst",
        knowledge_space_id=None,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    added: list = []
    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))
    assert len(added) == 1
    entity = added[0]
    assert entity.unique_id == f"{DAEMON}_calendar"
    # The entity belongs to the same device as the rest of the integration.
    assert (DOMAIN, runtime.device_identifier) in entity.device_info["identifiers"]


def test_calendar_is_registered_as_a_platform():
    """The calendar platform is actually forwarded at setup."""

    from custom_components.goodvibes.const import PLATFORMS

    assert "calendar" in PLATFORMS
