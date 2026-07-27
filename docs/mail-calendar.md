# Mail and Calendar

The GoodVibes daemon owns the mail and calendar accounts. This integration presents them the way
Home Assistant expects — a calendar entity, services, and a diagnostic sensor — and holds no
credentials of its own.

## The credential boundary

This is the whole design, and it is not negotiable:

- **No mail or calendar credential is ever stored in this repository or in Home Assistant.** There
  is no OAuth flow here, no client secret, no app password, no token. The integration does not
  import `imaplib`, `smtplib`, `caldav`, or any Google or Microsoft client library, and a test
  (`tests/test_mail_calendar.py::test_the_repo_contains_no_mail_or_calendar_credential_handling`)
  fails if one ever appears.
- **The Home Assistant config entry holds only the daemon connection** — daemon URL, daemon token,
  webhook secret — plus Home Assistant-side toggles. A second test asserts the config flow never
  grows a mail or calendar credential field.
- **The daemon owns the secrets**, in its own daemon-tier config, as `*Ref` handles into its secret
  store (`email.passwordRef`, `calendar.google.clientSecretRef`, `google.oauth.refreshToken`, and
  friends are all on the SDK's daemon-owned config path list). The integration never reads those
  values; it asks the daemon to act and the daemon uses its own account.

The consequence is the point: **configure mail or calendar once, on any surface, and every surface
has it.** The daemon persists daemon-owned config to `~/.goodvibes/daemon/settings.json`, so a
setting written from the TUI, the agent, or the web UI is visible here, and one written here works
for the daemon after Home Assistant restarts or the integration is reloaded. Verified against a
live daemon: setting a daemon-owned key returns
`{"tier": "daemon", "daemonOwned": true, "persistedTo": ".../.goodvibes/daemon/settings.json"}`,
and after a full daemon stop and restart a separate process reads the value back unchanged.

## What this integration exposes

### Calendar entity

A single `calendar.*` entity backed by the daemon's calendar. Events appear in Home Assistant's
calendar UI and work in automations like any other calendar. It supports creating events
(`CalendarEntityFeature.CREATE_EVENT`), which maps to `calendar.events.create`.

The entity is **unavailable**, not empty, when the daemon cannot serve the calendar — see below.
An empty calendar means "no events"; that is a different statement from "this was never set up",
and the two never look alike.

### Services

| Service | Daemon route | Authorization |
|---|---|---|
| `goodvibes.send_email` | `email.send` | admin |
| `goodvibes.create_email_draft` | `email.draft.create` | admin |
| `goodvibes.list_inbox` | `email.inbox.list` | open (read) |
| `goodvibes.read_email` | `email.inbox.read` | open (read) |
| `goodvibes.list_calendar_events` | `calendar.events.list` | open (read) |
| `goodvibes.get_calendar_event` | `calendar.events.get` | open (read) |

Sending mail and writing a draft act outside the house, so they are admin-gated the same way every
other writing service in this integration is. The reads are open so dashboards and non-admin users
can use them; the daemon's read routes use `EXAMINE`/`BODY.PEEK` and never mark a message as read.

`send_email` and event creation set the daemon's required `confirm: true` themselves — calling the
service *is* the explicit user action that flag is asking about, so it is not a field the user has
to remember to tick.

### Diagnostic sensor

`sensor.*_mail_and_calendar_status` reports `ready`, `needs_setup`, `unsupported`, `unavailable`
or `unknown`, with the concrete next step in its attributes.

## Reporting when it is not working

Three different things can be wrong, they have three different fixes, and conflating them is how a
user ends up staring at a blank calendar with no idea what to do. They stay distinct:

| State | What happened | What to do |
|---|---|---|
| `ready` | The daemon served the probe. | Nothing. |
| `needs_setup` | The routes are served, but no mail or calendar account is connected on the daemon. | Connect one on the daemon host, then reload the integration. |
| `unsupported` | The daemon does not serve the routes at all (HTTP 404). | Update the daemon to a release that serves them, then reload. |
| `unavailable` | The daemon could not be reached. | Check that it is running and that the URL and token are correct. |

Every non-ready state carries its next step, on the sensor and in the error raised by any service
call or calendar operation that hits it. Nothing fails silently and nothing surfaces as a bare
"unavailable".

## Deliberately not exposed

Stated explicitly, because these were considered and declined rather than overlooked:

- **Inbox messages as sensors.** Rejected. Home Assistant sensor state is capped at 255 characters
  and every state change is written to the recorder database; a mailbox turned into entities would
  bloat the database, and message subjects would land in long-term history. `list_inbox` and
  `read_email` return their data as service responses instead, which is the right shape for
  "fetch this when I ask" and leaves no recorder trail. The count-style summary that *would* suit a
  sensor is not exposed yet because the daemon does not serve the routes at all, so there is no
  honest number to show.
- **A `notify` entity.** Rejected in favour of the `goodvibes.send_email` service. Home Assistant's
  `NotifyEntity.send_message` takes a message and an optional title but has **no recipient**, and
  this integration has no configured default recipient to fall back on (a recipient would be
  account configuration, which is daemon-owned). A notify entity would therefore be unable to
  express the one field an email most needs. The service takes `to`, `subject` and `body` and
  matches both the daemon contract and this repo's established service pattern.
- **Event update and delete.** The daemon's contract has no update or delete route for calendar
  events, so `CalendarEntityFeature.UPDATE_EVENT` and `DELETE_EVENT` are not advertised. Claiming
  a capability the daemon cannot perform would put a button in the UI that always fails.
- **`calendar.ics.export` / `calendar.ics.import`.** Served by the daemon's contract but not
  surfaced. Home Assistant has no natural place for raw iCalendar blobs, and import is a bulk
  destructive-ish operation better run from a surface with a real confirmation step.

## Current daemon status

As of the SDK release this integration is validated against (`1.17.2`), all seven mail and calendar
routes are declared in the operator contract but carry `invokable: false`, and a live daemon
answers `404` on every one of them. The integration therefore reports `unsupported` and the
calendar entity stays unavailable with that reason attached — which is the honest state, and
exactly what this surface is built to say.

Nothing here needs to change when the daemon starts serving them: the route paths come from the
contract's own `http.path` bindings, and the state flips to `ready` on the next refresh.
`scripts/validate-daemon-contract.mjs` prints the served/not-served status of each route on every
run, so the transition is visible the moment it happens.
