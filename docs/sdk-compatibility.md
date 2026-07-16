# SDK Compatibility

This integration targets the **latest** published `@pellux/goodvibes-sdk`, always. It is a thin
client over stable daemon HTTP routes, not a build pinned to one SDK release, so there is no
per-release "target" number to chase. What matters is the daemon contract — the HTTP routes and
JSON response shapes — which the integration reads directly.

The single moving label is the newest npm version the daemon contract was last **validated
against**. It lives in one place, `const.SDK_VALIDATED_VERSION`, and CI echoes it against the live
`npm view @pellux/goodvibes-sdk version` as an informational nudge (it never fails the build) so a
drift is visible without gating releases.

## Current State

- **Target:** latest `@pellux/goodvibes-sdk`.
- **Last validated against:** `1.10.1` (`const.SDK_VALIDATED_VERSION`), validated 2026-07-16.

Because the integration calls raw daemon HTTP routes rather than the SDK operator-method catalog,
the SDK's `1.0` breaking renames (which reshaped the operator method catalog) did not touch it —
every route the integration calls is intact at `1.10.1`. A pin-forward to a newer SDK is therefore
a validation-and-docs pass, not a code rewrite; the only real risk is response-shape drift inside
JSON bodies, which the checks below and the test suite guard against.

The 2026-07-16 pass re-vendored `custom_components/goodvibes/generated_client.py` byte-for-byte
from the published `1.10.1` package's own generated Python artifact
(`dist/contracts/artifacts/python/homeassistant_operator_client.py`, extracted from
`@pellux/goodvibes-sdk@1.10.1` on npm). The only diff from `1.10.0` is the version label itself
(`Contract product version: 1.10.1` and `CONTRACT_VERSION = "1.10.1"`); the operator contract's
REST subset this client depends on (33 methods) and all its route bindings and types are
byte-for-byte unchanged, so 1.10.1 (a patch release adding type aliases and export subpaths only)
did not touch the HA-consumed method set at all. This pass also booted a daemon from the published
`1.10.1` SDK (isolated home directory, isolated working directory, ephemeral loopback port, Home
Assistant surface enabled — composed via the SDK's own published `bootDaemon` factory from
`@pellux/goodvibes-sdk/daemon`, stopped in a `finally` block) and re-ran the validation checklist
against it: `/status` (including a bad-token `401`, reporting `version: 1.10.1`),
`/api/homeassistant/health` (capabilities include `conversation-stream` and `conversation-cancel`),
the manifest action, and the Home Graph status/sync/ask/pages/map/reindex/issues/refinement-run
routes all returned the expected shapes, and the conversation, conversation/stream, and
conversation/cancel routes returned the expected results, including a full streamed frame envelope
(`delta` frames followed by a terminal `final` frame) and a real assistant reply. This repo's full
local check recipe from `docs/development.md` (`python -m compileall`, the frontend JS syntax
check, the release-metadata consistency check, `git diff --check`, and the full `pytest` suite)
passed against it, including the response-shape assertions below and
`test_version_check.py::test_contract_version_is_at_least_min_daemon_version`.

After upgrading or restarting the daemon SDK during live validation, restart Home Assistant once
the daemon reports healthy so the integration reopens its daemon client.

## Response-shape Validation

The daemon response shapes the integration reads most directly were checked against the current
GoodVibes SDK daemon router source and confirmed intact. These are also encoded as assertions in
the test suite, so a future SDK change that renames one of these fields is caught in CI.

- `GET /status` returns `status` and `version`, and returns HTTP `401` when the bearer token is
  rejected. The daemon status sensor and the config flow read both fields.
- `GET /api/homeassistant/home-graph/status` returns `ok` plus the graph counts (`sourceCount`,
  `nodeCount`, `edgeCount`, `issueCount`) and a `readiness` block. The Home Graph status sensor
  treats `ok: true` as ready.
- `GET /api/homeassistant/home-graph/issues` returns `ok`, `spaceId`, and an `issues` list. The
  issues sensor counts the list length.
- `POST /api/homeassistant/conversation` returns `status`, `mode`, `sessionId`, `messageId`, and,
  on a completed turn, an `assistant` object with `speechText` and `text`. The Assist agent reads
  all of these.
- `POST /api/homeassistant/conversation/stream` streams incremental `event: delta` frames shaped
  `{ ok, delta, text, turnId, conversationId?, messageId? }` as the model produces text, followed by
  the unchanged terminal `final` (or `error`) frame. The Assist agent consumes this stream and
  renders it through Home Assistant's conversation delta-stream API, reading each frame's `delta`
  field (the incremental chunk, not the running `text` accumulation).
- `POST /api/homeassistant/home-graph/refinement/run` accepts an optional `triage` input
  (`{ minConfidence, limit, chunkSize, force, skipIssueIds, reviewer }`) and returns a `triage`
  object (`{ ok, spaceId, configured, processed, skipped, applied, reviewed, decisions[],
  remaining, minConfidence, reason? }`). The GoodVibes Home panel's automatic issue triage calls
  this instead of running its own local classification: `configured: false` (or an HTTP `404` on
  the `triage` input, from a daemon that predates it) means the daemon has no server-side triage
  available, and the integration reports that honestly instead of falling back to a local engine.
- `POST /api/channels/actions/homeassistant/homeassistant-manifest` wraps its result as
  `{ actionId, surface, result: { device: { identifiers, manufacturer, model, name }, ... } }`.
  The integration unwraps `result` and reads the `device` fields, falling back to the daemon status
  `version` when the device object has no `swVersion`.

## Minimum Expected Daemon Surface

The config flow validates:

- `GET /status`
- `GET /api/homeassistant/health`
- `POST /api/channels/actions/homeassistant/homeassistant-manifest`
- `GET /api/homeassistant/home-graph/status` when Home Graph is enabled

Assist uses:

- `POST /api/homeassistant/conversation/stream` (streamed), alongside
  `POST /api/homeassistant/conversation`.

Home Graph uses the daemon routes listed in [home-graph.md](home-graph.md#daemon-routes).

## Validation Checklist

After a daemon SDK update, and after refreshing `const.SDK_VALIDATED_VERSION`:

1. Check `GET /status`.
2. Check `GET /api/homeassistant/health`.
3. Restart Home Assistant after the daemon is healthy.
4. Open the `GoodVibes Home` panel.
5. Run `goodvibes.sync_home_graph`.
6. Ask a source-backed Home Graph question.
7. Load generated pages.
8. Load the visual map.
9. Run `goodvibes.home_graph_reindex` if old uploads need reparsing or semantic enrichment.
10. Test Assist through a Home Assistant Assist pipeline.

## Contract Rules

The integration should continue to follow these rules when SDK behavior changes:

- Keep graph storage, search, page generation, packets, artifacts, answer synthesis, and map layout
  daemon-owned.
- Render daemon-provided fields directly instead of inferring graph linkage locally.
- Preserve SDK fields such as `answer.refinement`, `answer.refinementTaskIds`, `facts`, `gaps`,
  `linkedObjects`, `sources`, `subject`, `subjectIds`, `linkedObjectIds`, and `targetHints`.
- Send map filters to the daemon and display returned SVG/facets.
- Use the SDK reset route for destructive Home Graph reset. Do not implement reset through local
  database edits.
- Use export/import only for backup and transfer, not reset.
