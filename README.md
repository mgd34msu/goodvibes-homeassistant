# GoodVibes Home Assistant integration

[![CI](https://github.com/mgd34msu/goodvibes-homeassistant/actions/workflows/ci.yml/badge.svg)](https://github.com/mgd34msu/goodvibes-homeassistant/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-0.13.11-blue.svg)](https://github.com/mgd34msu/goodvibes-homeassistant)

GoodVibes is a conversational assistant that runs as its own daemon; this integration is the Home Assistant side of it. It adds a `GoodVibes` conversation entity you can select as the agent in an Assist pipeline, an admin-only `GoodVibes Home` sidebar panel for browsing and feeding the daemon's Home Graph knowledge base, diagnostic sensors and repairs, an update entity, and a set of Home Assistant services for prompting, running agents, and working with Home Graph facts and pages. The daemon owns the model, routing, knowledge storage, and answer synthesis; this integration stays thin: setup, Assist plumbing, services, sensors, upload proxying, and the panel bridge.

<img src="docs/assets/home-graph-map.png" alt="The GoodVibes Home panel open in the Home Assistant sidebar, on its Map tab. The header reads GoodVibes Home, ok - ready, with Refresh, Sync, and Reindex uploads buttons and a tab row of Browse, Map, Ingest, Ask, Link, Refine, Review, and Pages. A facet column on the left lists integrations found in this instance: shopping list, backup, goodvibes, google translate, met, and radio browser; plus domains, objects, entities, and integration IDs. To the right, the Home Graph Map draws a central Demo Home node linked out to Radio Browser, Shopping list, Shopping List, Home, Backup, Google Translate, and GoodVibes. A summary line reads 8 nodes, 8 edges, 16 matching records, homeassistant:demo-home." width="900">

---

## Install

### HACS

1. Add this repository as a custom repository in HACS (category: Integration), or find it if already listed.
2. Install `GoodVibes` from HACS.
3. Restart Home Assistant.

### Manual

1. Download `goodvibes.zip` from the [latest release](https://github.com/mgd34msu/goodvibes-homeassistant/releases) and unzip it, or copy `custom_components/goodvibes` from a checkout of this repository.
2. Place `goodvibes` inside your Home Assistant `custom_components` directory.
3. Restart Home Assistant.

Either way, you also need a running GoodVibes daemon (from `@pellux/goodvibes-sdk`) with its Home Assistant surface enabled. See [Setup](#setup) below.

After installing an update, restart Home Assistant again so the new Python and frontend files load; reloading the config entry is not enough. Updates arrive as GitHub releases tagged `vX.Y.Z`, each shipping a `goodvibes.zip` asset that Home Assistant's own update entity can install.

---

## Setup

Enable the Home Assistant surface in the GoodVibes daemon config first:

```json
{
  "featureFlags": {
    "homeassistant-surface": "enabled"
  },
  "surfaces": {
    "homeassistant": {
      "enabled": true,
      "instanceUrl": "http://homeassistant.local:8123",
      "accessToken": "goodvibes://...",
      "webhookSecret": "...",
      "eventType": "goodvibes_message"
    }
  }
}
```

The Home Assistant long-lived access token belongs there, as `surfaces.homeassistant.accessToken`. It lets the daemon call back into Home Assistant for state, service, template, and event tools. It is not what authenticates Home Assistant's requests to the daemon.

Then, in Home Assistant, add the integration from **Settings → Devices & services → Add integration → GoodVibes**:

| Field | What it's for |
| --- | --- |
| Daemon URL | Base URL of the GoodVibes daemon, e.g. `http://127.0.0.1:3421` |
| Daemon bearer token or pairing token | Authenticates Home Assistant's requests to the daemon: the companion/operator token from the TUI/daemon pairing flow |
| Home Assistant webhook secret | Shared secret protecting `/webhook/homeassistant`; must match the daemon's `surfaces.homeassistant.webhookSecret` |
| Home Assistant event type | Event bus type the daemon publishes to; default `goodvibes_message` |
| Enable Home Graph | Turns on Home Graph sensors, services, and the sidebar panel's Home Graph features |
| Include entities not exposed to assistants | Widens the Home Graph snapshot and perception triggers beyond assistant-exposed entities |
| Home Graph installation ID | Stable installation id; blank derives it from `hass.config.uuid` |
| Home Graph knowledge space ID | Explicit daemon knowledge space; blank uses `homeassistant:<installationId>` |

A daemon bearer token or pairing token is required for every normal daemon API call; the webhook secret only covers the webhook path. See [docs/security.md](docs/security.md) for how the three credential roles (daemon token, webhook secret, Home Assistant access token) fit together, and where each one is stored.

After the initial setup, **Configure** on the integration opens a second options step that shapes each Assist turn and two opt-in local features, all off or unset by default: a custom prompt and a Home Assistant LLM API (control tools and live context) forwarded to the daemon as the turn's instructions; perception triggers, which start an attributed daemon session when a chosen entity's state changes; and habit mining, which watches your own observation history in memory and proposes, never silently creates, recurring-pattern automations. See [docs/conversation.md](docs/conversation.md) and [docs/habits.md](docs/habits.md).

Restart Home Assistant once, after the daemon reports healthy, whenever you upgrade or restart the daemon during live use. This makes the integration reopen its daemon client instead of reusing a stale one.

---

## What you get

Each row links to the page that documents it in full.

| Area | What you get | Docs |
| --- | --- | --- |
| Assist conversation agent | A selectable Assist agent that streams daemon replies through Home Assistant's own delta-stream API; adopts Home Assistant's prompt/LLM-API options layer while the daemon keeps running the model and controlling the home | [conversation.md](docs/conversation.md) |
| Voice | The conversation entity works as the agent behind a [Wyoming](https://www.home-assistant.io/integrations/wyoming/) satellite: wake word, STT, and TTS stay with Home Assistant and Wyoming | [voice-assist.md](docs/voice-assist.md) |
| GoodVibes Home panel | Admin-only sidebar UI for Home Graph status, sync, source/node/edge/issue browsing, the visual map, URL/note/file ingest, source-backed questions, link/unlink, review, reindex, generated pages, export and import, reset, and packets; talks to Home Assistant, never directly to the daemon | [home-graph.md](docs/home-graph.md) |
| Home Assistant services | `goodvibes.prompt`, `run_agent`, `status`, `cancel`, `call_tool`; the Home Graph service set (`sync_home_graph`, `ingest_url`, `ingest_note`, `ingest_artifact`, `ask_home_graph`, `link_knowledge`, and more); `causal_chain`; `habit_proposals` and `accept_habit` | [services.md](docs/services.md) |
| Mail and calendar | A calendar entity backed by the daemon's calendar (events in the calendar UI and usable in automations, including event creation), plus `send_email`, `create_email_draft`, `list_inbox`, `read_email`, `list_calendar_events` and `get_calendar_event`. The daemon owns the accounts and every credential; nothing is stored here, so setup done on any surface works on all of them | [mail-calendar.md](docs/mail-calendar.md) |
| Perception triggers | Opt-in: a state change on a chosen entity starts an attributed daemon session carrying the triggering context; rate-limited, admin-gated, honors the exposed-entities boundary | [conversation.md](docs/conversation.md) |
| Habit mining | Opt-in, in-memory-only pattern detection over your own observation history, surfaced as automation proposals you review and explicitly accept | [habits.md](docs/habits.md) |
| Causal provenance | Attributes a recent state change to its likely cause from the Home Assistant context chain, admin-gated | [causal-provenance.md](docs/causal-provenance.md) |
| Sensors, repairs, update | Diagnostic sensors for daemon status, last reply, active session/message/agent IDs, tool catalog, Home Graph status/issues/sources and mail/calendar status; repairs for Home Graph availability and unresolved issues; a GitHub-release-backed update entity | n/a |
| Event handling | Daemon replies post back to Home Assistant's REST event bus (`POST /api/events/<event type>`, default `goodvibes_message`); the webhook path handles queued async automation calls | [security.md](docs/security.md) |
| Security and credentials | The three credential roles, storage, browser-token boundary, upload handling, rotation order | [security.md](docs/security.md) |
| Known limits | Upload size and timeouts, stale daemon clients, reset vs. import, release delivery, restart requirements | [known-limits.md](docs/known-limits.md) |
| Troubleshooting | Common setup, auth, Home Graph, Assist, and upload problems | [troubleshooting.md](docs/troubleshooting.md) |

Full index: [docs/README.md](docs/README.md).

<img src="docs/assets/home-panel.png" alt="The GoodVibes Home panel on its Browse tab inside Home Assistant. A Home Graph card reports status ok, the knowledge space homeassistant:demo-home, the last sync timestamp, 8 sources, 8 nodes, 15 edges, 0 issues, 0 extractions, a readiness line reading ready with no open issues or active tasks, and the daemon's advertised capability list. Beside it a Filter card offers a text query and a result limit. Below, a Sources card and a Nodes card show the indexed records as formatted JSON: a Home Assistant documentation source and a Shopping List entity node." width="900">

---

## Compatibility

This integration targets the **latest** published `@pellux/goodvibes-sdk`, always. It is a thin client over stable daemon HTTP routes, not a build pinned to one SDK release, so there is no per-release version to chase. The single moving label is the newest npm version the daemon contract was last validated against, tracked in `const.SDK_VALIDATED_VERSION`. That claim is enforced: a test fails when the label and the vendored contract artifact disagree, a scheduled `SDK drift` workflow fails when the label falls behind npm, and `scripts/validate-daemon-contract.mjs` runs the live checklist against a daemon it boots itself.

`docs/sdk-compatibility.md` is the source of truth for the current validated version, the response-shape checks the test suite guards, and the full validation history. Read it before pinning to a specific daemon build.

---

## Boundaries

This integration intentionally stays thin. It does not implement GoodVibes model or provider routing, local Home Graph storage, daemon knowledge-wiki rendering, or local graph layout, and it does not manage the Home Assistant long-lived access token used by the daemon. The daemon is the source of truth; Home Assistant supplies context, service calls, sensors, repairs, Assist plumbing, and event handling. See [docs/known-limits.md](docs/known-limits.md) for the operational limits that follow from this split.

---

## Development

```sh
git clone https://github.com/mgd34msu/goodvibes-homeassistant.git
cd goodvibes-homeassistant
python -m venv .venv-test
.venv-test/bin/pip install -r requirements_test.txt
.venv-test/bin/python -m pytest
```

The sidebar panel is authored in `frontend/src/` and built with esbuild into the served `custom_components/goodvibes/frontend/` directory. The built output is committed, since Home Assistant installs never run a build step:

```sh
cd frontend
npm ci
npm run build
```

Before pushing, also run the same syntax and metadata checks CI runs:

```sh
python -m compileall custom_components/goodvibes
find custom_components/goodvibes/frontend -name '*.js' -print0 | xargs -0 -r -n1 node --check
```

CI additionally runs the pytest suite, Home Assistant's own `hassfest` validation, and HACS validation; a push to `main` that clears all of them tags and publishes a release automatically. The full local check recipe, release process, and version-bump checklist are in [docs/development.md](docs/development.md).

---

## License

MIT
