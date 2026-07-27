"""Mail and calendar: honest state reporting and daemon-owned credentials.

The point of these tests is that the integration never guesses and never goes
quiet. A daemon that does not serve the routes, a daemon with no account
connected, and an unreachable daemon are three different conditions with three
different fixes, and each has to surface as itself with its own next step.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.goodvibes import services as svc
from custom_components.goodvibes.client import (
    GoodVibesDaemonError,
    GoodVibesSurfaceMissingError,
    GoodVibesUnavailableError,
)
from custom_components.goodvibes.const import (
    DOMAIN,
    MAIL_CALENDAR_NEEDS_SETUP,
    MAIL_CALENDAR_READY,
    MAIL_CALENDAR_UNAVAILABLE,
    MAIL_CALENDAR_UNSUPPORTED,
)
from custom_components.goodvibes.data import GoodVibesRuntimeData
from custom_components.goodvibes.mail_calendar import (
    async_probe,
    classify_error,
    event_payload,
    event_window,
    normalize_events,
    parse_timestamp,
)

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
    """A daemon client double whose calendar route outcome is settable."""

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

    async def email_send(self, payload):
        self.sent.append(("email_send", dict(payload)))
        if self.error is not None:
            raise self.error
        return {"messageId": "msg-1"}


def _runtime(hass, client) -> GoodVibesRuntimeData:
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
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    return runtime


async def _runtime_with_services(hass, client) -> GoodVibesRuntimeData:
    """Register the runtime and the real service handlers on it."""

    runtime = _runtime(hass, client)
    await svc.async_setup_services(hass)
    return runtime


# --------------------------------------------------------------------------
# Classification: the three failures stay distinct
# --------------------------------------------------------------------------


def test_404_is_reported_as_unsupported_not_as_a_generic_failure():
    """A daemon that does not serve the routes is 'unsupported', with a fix."""

    state, detail = classify_error(
        GoodVibesSurfaceMissingError("GoodVibes HTTP 404: Route not found", status=404)
    )
    assert state == MAIL_CALENDAR_UNSUPPORTED
    assert "404" in detail


def test_unreachable_daemon_is_not_confused_with_an_unconfigured_one():
    state, _ = classify_error(GoodVibesUnavailableError("connection refused"))
    assert state == MAIL_CALENDAR_UNAVAILABLE


@pytest.mark.parametrize(
    "message",
    [
        "GoodVibes HTTP 400: mail account is not configured",
        "GoodVibes HTTP 412: no account connected",
        "GoodVibes HTTP 400: missing credentials for calendar",
        "GoodVibes HTTP 409: calendar is unconfigured",
    ],
)
def test_no_account_connected_is_reported_as_needs_setup(message):
    """A served route with nothing behind it is 'needs setup', not a fault."""

    state, _ = classify_error(GoodVibesDaemonError(message, status=400))
    assert state == MAIL_CALENDAR_NEEDS_SETUP


def test_an_unrelated_daemon_error_does_not_condemn_the_surface():
    """One failed call is not evidence the whole surface is unusable."""

    state, _ = classify_error(GoodVibesDaemonError("HTTP 500: internal", status=500))
    assert state == MAIL_CALENDAR_READY


@pytest.mark.parametrize(
    "code",
    ["EMAIL_NOT_CONFIGURED", "CALENDAR_NOT_CONFIGURED", "EMAIL_CREDENTIALS_MISSING"],
)
def test_the_machine_code_decides_not_the_wording(code):
    """The daemon's code classifies it, whatever the sentence happens to say.

    This is the regression that made the whole check necessary. When the daemon
    started serving these routes for real it answered

        HTTP 400 {"error": "No Google account is connected on this machine, so
        there is no calendar to read or write. Connect one, then retry.",
        "code": "CALENDAR_NOT_CONFIGURED"}

    and the substring list of the day held "no account", "not connected" and
    "not configured" — none of which appear in "No Google account is
    connected". The classifier fell through to its ready default, so a calendar
    with nothing behind it would have reported itself READY. The message here is
    deliberately one that matches no hint at all.
    """

    state, _ = classify_error(
        GoodVibesDaemonError(
            "GoodVibes HTTP 400: No Google account is connected on this machine, "
            "so there is no calendar to read or write. Connect one, then retry.",
            status=400,
            code=code,
        )
    )
    assert state == MAIL_CALENDAR_NEEDS_SETUP


def test_a_route_that_is_real_but_unwired_is_unsupported_not_needs_setup():
    """501 NOT_INVOKABLE is a daemon composition fact, not a missing account.

    The daemon is current and the route exists; what is absent is a handler in
    the composition it was built with. Reporting that as needs_setup would send
    someone to connect an account that would still not be reachable.
    """

    state, _ = classify_error(
        GoodVibesSurfaceMissingError(
            "GoodVibes HTTP 501: Gateway method is not invokable: email.inbox.list",
            status=501,
            code="NOT_INVOKABLE",
        )
    )
    assert state == MAIL_CALENDAR_UNSUPPORTED


def test_a_daemon_with_no_machine_code_still_classifies_on_the_wording():
    """The prose fallback stays, for a daemon old enough to answer without one."""

    state, _ = classify_error(
        GoodVibesDaemonError("GoodVibes HTTP 400: mail is not configured", status=400)
    )
    assert state == MAIL_CALENDAR_NEEDS_SETUP


def test_every_non_ready_state_carries_a_concrete_next_step(hass):
    """No state is ever reported without telling the user what to do."""

    from custom_components.goodvibes.mail_calendar import MailCalendarState

    for state in (
        MAIL_CALENDAR_NEEDS_SETUP,
        MAIL_CALENDAR_UNSUPPORTED,
        MAIL_CALENDAR_UNAVAILABLE,
    ):
        holder = MailCalendarState(state=state)
        assert holder.next_step, f"{state} has no next step"
        assert not holder.ready
        # The message raised at a user names the action and the fix.
        message = holder.error_message("send the email")
        assert "send the email" in message
        assert holder.next_step in message


# --------------------------------------------------------------------------
# Probing
# --------------------------------------------------------------------------


async def test_probe_reports_ready_and_keeps_the_events():
    client = _CalendarClient(
        events=[{"id": "1", "title": "Standup", "start": "2026-08-01T09:00:00+00:00"}]
    )
    state = await async_probe(client)
    assert state.state == MAIL_CALENDAR_READY
    assert state.ready
    assert len(state.events) == 1
    assert state.checked_at


async def test_probe_on_a_daemon_without_the_routes_reports_unsupported():
    client = _CalendarClient(
        error=GoodVibesSurfaceMissingError("HTTP 404: Route not found", status=404)
    )
    state = await async_probe(client)
    assert state.state == MAIL_CALENDAR_UNSUPPORTED
    assert state.events == []
    assert "Update the daemon" in state.next_step


async def test_refresh_records_mail_calendar_state_without_raising(hass):
    """A daemon with no mail/calendar must not break the ordinary refresh."""

    client = _CalendarClient(
        error=GoodVibesSurfaceMissingError("HTTP 404", status=404)
    )
    runtime = _runtime(hass, client)
    await runtime.async_refresh_mail_calendar()
    assert runtime.mail_calendar.state == MAIL_CALENDAR_UNSUPPORTED


async def test_a_failed_call_updates_the_reported_state_immediately(hass):
    """A live failure must not leave a stale 'ready' until the next refresh."""

    client = _CalendarClient()
    runtime = _runtime(hass, client)
    await runtime.async_refresh_mail_calendar()
    assert runtime.mail_calendar.ready

    runtime.async_apply_mail_calendar_error(
        GoodVibesSurfaceMissingError("HTTP 404", status=404)
    )
    assert runtime.mail_calendar.state == MAIL_CALENDAR_UNSUPPORTED
    assert runtime.mail_calendar.events == []


# --------------------------------------------------------------------------
# Timestamp and payload handling
# --------------------------------------------------------------------------


def test_a_date_only_timestamp_stays_an_all_day_date():
    parsed = parse_timestamp("2026-08-01")
    assert isinstance(parsed, date) and not isinstance(parsed, datetime)


def test_a_zoned_timestamp_is_preserved():
    parsed = parse_timestamp("2026-08-01T09:00:00+00:00")
    assert isinstance(parsed, datetime)
    assert parsed.tzinfo is not None


def test_an_unparseable_timestamp_is_rejected_rather_than_guessed():
    assert parse_timestamp("not a time") is None
    assert parse_timestamp("") is None
    assert parse_timestamp(None) is None


def test_an_event_without_an_end_gets_a_default_rather_than_being_dropped():
    window = event_window({"start": "2026-08-01T09:00:00+00:00"})
    assert window is not None
    start, end = window
    assert end - start == timedelta(hours=1)


def test_an_event_without_a_start_is_dropped():
    assert event_window({"end": "2026-08-01T10:00:00+00:00"}) is None


def test_an_event_ending_before_it_starts_is_dropped():
    assert (
        event_window(
            {"start": "2026-08-01T10:00:00+00:00", "end": "2026-08-01T09:00:00+00:00"}
        )
        is None
    )


def test_mixed_all_day_and_timed_ends_are_dropped():
    """Home Assistant requires both ends to be the same kind."""

    assert event_window({"start": "2026-08-01", "end": "2026-08-01T10:00:00+00:00"}) is None


def test_normalize_events_tolerates_a_malformed_response():
    assert normalize_events(None) == []
    assert normalize_events({}) == []
    assert normalize_events({"events": "nope"}) == []
    assert normalize_events({"events": [{"id": "1"}, "junk"]}) == [{"id": "1"}]


def test_event_payload_maps_ha_fields_onto_the_daemon_contract():
    payload = event_payload(
        {
            "summary": "Dentist",
            "description": "Checkup",
            "location": "Clinic",
            "start": datetime(2026, 8, 1, 9, 0, tzinfo=dt_util.UTC),
            "end": datetime(2026, 8, 1, 10, 0, tzinfo=dt_util.UTC),
        }
    )
    assert payload["title"] == "Dentist"
    assert payload["description"] == "Checkup"
    assert payload["location"] == "Clinic"
    assert payload["start"].startswith("2026-08-01T09:00")
    # The daemon requires explicit confirmation on an event create; the service
    # call itself is that explicit action.
    assert payload["confirm"] is True


def test_event_payload_omits_fields_the_user_did_not_supply():
    payload = event_payload({"summary": "Bare"})
    assert "description" not in payload
    assert "location" not in payload
    assert "attendees" not in payload


# --------------------------------------------------------------------------
# Services
# --------------------------------------------------------------------------


async def test_send_email_sets_confirm_and_never_carries_a_credential(hass):
    """The daemon owns the account: the payload is a message, not a login."""

    client = _CalendarClient()
    await _runtime_with_services(hass, client)
    await hass.services.async_call(
        DOMAIN,
        "send_email",
        {"to": "a@example.com", "subject": "Hi", "body": "There"},
        blocking=True,
    )
    name, payload = client.sent[-1]
    assert name == "email_send"
    assert payload["to"] == "a@example.com"
    assert payload["confirm"] is True
    for forbidden in ("password", "token", "secret", "credential", "oauth", "apiKey"):
        assert not any(forbidden.lower() in key.lower() for key in payload)


async def test_a_mail_service_on_a_daemon_without_the_routes_says_what_to_do(hass):
    """Never a bare failure: the error names the fix."""

    client = _CalendarClient(
        error=GoodVibesSurfaceMissingError("HTTP 404: Route not found", status=404)
    )
    runtime = await _runtime_with_services(hass, client)
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN,
            "send_email",
            {"to": "a@example.com", "subject": "Hi", "body": "There"},
            blocking=True,
        )
    assert "Update the daemon" in str(err.value)
    assert runtime.mail_calendar.state == MAIL_CALENDAR_UNSUPPORTED


async def test_a_mail_service_with_no_account_connected_says_to_connect_one(hass):
    client = _CalendarClient(
        error=GoodVibesDaemonError("HTTP 400: mail account is not configured", status=400)
    )
    await _runtime_with_services(hass, client)
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN,
            "send_email",
            {"to": "a@example.com", "subject": "Hi", "body": "There"},
            blocking=True,
        )
    assert "Connect one on the daemon host" in str(err.value)


async def test_list_calendar_events_maps_start_end_onto_the_daemon_window(hass):
    client = _CalendarClient()
    await _runtime_with_services(hass, client)
    await hass.services.async_call(
        DOMAIN,
        "list_calendar_events",
        {"start": "2026-08-01T00:00:00Z", "end": "2026-08-31T00:00:00Z"},
        blocking=True,
        return_response=True,
    )
    _, payload = client.sent[-1]
    assert payload["from"] == "2026-08-01T00:00:00Z"
    assert payload["to"] == "2026-08-31T00:00:00Z"


# --------------------------------------------------------------------------
# The credential boundary
# --------------------------------------------------------------------------


def test_the_repo_contains_no_mail_or_calendar_credential_handling():
    """This repo must never grow a mail/calendar client or credential store.

    The daemon owns the accounts and the secrets (they live under its own
    daemon-tier config as ``*Ref`` handles into its secret store). Home
    Assistant asks the daemon; it never authenticates to a mail or calendar
    provider itself. A direct provider dependency appearing here would mean
    that boundary had been crossed.
    """

    import pathlib

    component = pathlib.Path(__file__).resolve().parents[1] / "custom_components/goodvibes"
    banned = (
        "imaplib",
        "smtplib",
        "caldav",
        "google.oauth2",
        "googleapiclient",
        "google_auth_oauthlib",
        "msal",
    )
    offenders = []
    for path in component.rglob("*.py"):
        text = path.read_text()
        for token in banned:
            if f"import {token}" in text or f"from {token}" in text:
                offenders.append(f"{path.name}: {token}")
    assert not offenders, (
        "The integration must not talk to a mail or calendar provider directly; "
        f"the daemon owns those accounts. Found: {offenders}"
    )


def test_the_config_entry_never_stores_a_mail_or_calendar_credential():
    """Config-entry data is the daemon connection only.

    Anything configured on any surface belongs in daemon-owned config, so it is
    available to every surface and survives Home Assistant restarts and
    integration reloads. A mail or calendar credential stored in Home
    Assistant's own config entry would be invisible to the other surfaces and
    would duplicate a secret the daemon already owns.
    """

    from custom_components.goodvibes import config_flow

    source = (
        __import__("pathlib").Path(config_flow.__file__).read_text()
    )
    for banned in (
        "google_client_secret",
        "imap_password",
        "smtp_password",
        "refresh_token",
        "oauth_token",
        "mail_password",
        "calendar_password",
    ):
        assert banned not in source, (
            f"config_flow.py must not collect {banned}: mail and calendar "
            "credentials are daemon-owned."
        )
