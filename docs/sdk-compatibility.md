# SDK compatibility

This integration targets the **latest** published `@pellux/goodvibes-sdk`, always. It is a thin
client over stable daemon HTTP routes, not a build pinned to one SDK release, so there is no
per-release "target" number to chase. What matters is the daemon contract: the HTTP routes and
JSON response shapes, which the integration reads directly.

The single moving label is the newest npm version the daemon contract was last **validated
against**. It lives in one place, `const.SDK_VALIDATED_VERSION`.

## How the claim is enforced

Until 2026-07-27 it was enforced by nothing, and it drifted five releases without anything going
red. That is worth stating plainly, because it explains the drift:

- CI's `SDK version nudge` step is an `echo` plus a `::notice::`. It is explicitly informational
  and **cannot fail the build**. A notice in a passing job's log is not a gate.
- `tests/test_generated_client_sync.py`, the one mechanical check that compares the vendored
  client against the SDK artifact, `pytest.skip`s unless a sibling `goodvibes-sdk` checkout
  happens to exist next to this repo. CI has no SDK checkout, so it skipped on every run.
- `test_version_check.py::test_contract_version_is_at_least_min_daemon_version` only asserts
  `CONTRACT_VERSION >= MIN_DAEMON_VERSION`, and that floor is `1.3.0`. It passes for every release
  that will ever ship.
- The live half existed only as prose in this file: booting a daemon, probing the routes. Every
  pass hand-rolled a throwaway script, so there was nothing to re-run and nothing to fail.

Three of those four could not fail by construction. Three checks now do:

1. **`test_version_check.py::test_validated_version_matches_vendored_contract`** (runs in CI, no
   network) fails when `const.SDK_VALIDATED_VERSION` and the vendored
   `generated_client.CONTRACT_VERSION` disagree. Claiming validation at a version whose artifact
   is not the one vendored here is now impossible.
2. **`scripts/validate-daemon-contract.mjs`** (`bun scripts/validate-daemon-contract.mjs [version]`)
   is the live checklist as a runnable program: it installs the published SDK, diffs the vendored
   client against the release artifact, boots a daemon in a throwaway home on an ephemeral port,
   probes every route this integration consumes, checks the documented response shapes, and exits
   non-zero on any failure. It stops the daemon in a `finally` block and never touches a running
   one.
3. **`.github/workflows/sdk-drift.yml`** runs weekly and **fails** when the validated pin is behind
   `npm view @pellux/goodvibes-sdk version`. It is deliberately not part of `ci.yml`: the drift
   depends on npm's publish cadence, not on the commit, so gating pushes or the auto-release on it
   would block this repo's releases on another repo's publishes. A red scheduled run is visible in
   the Actions list in a way a passing job's log notice never was.

## Current state

- **Target:** latest `@pellux/goodvibes-sdk`.
- **Last validated against:** `1.21.0` (`const.SDK_VALIDATED_VERSION`), validated 2026-07-30.

Because the integration calls raw daemon HTTP routes rather than the SDK operator-method catalog,
the SDK's `1.0` breaking renames (which reshaped the operator method catalog) did not touch it.
Every route the integration calls is intact at `1.10.1`. A pin-forward to a newer SDK is therefore
a validation-and-docs pass, not a code rewrite; the only real risk is response-shape drift inside
JSON bodies, which the checks below and the test suite guard against.

The `1.21.0` pass (2026-07-30) followed the `1.20.0` pass by a single release. It re-vendored
`custom_components/goodvibes/generated_client.py` byte-for-byte from the published `1.21.0`
package's Python artifact; the only diff from `1.20.0` is the contract version label, so all 33
consumed methods, routes and types are unchanged.

This pass also diffed both releases' `operator-contract.json` artifacts directly rather than
inferring from the vendored client alone: the method list is identical between `1.20.0` and
`1.21.0`: 483 methods, none added or removed. The daemon-lifecycle work that shipped in this
span did not touch the operator contract at all.

`scripts/validate-daemon-contract.mjs 1.21.0` passed every check against a daemon booted from the
published `1.21.0` SDK in an isolated home on an ephemeral loopback port: `/status` returns
`status: running` / `version: 1.21.0` and `401` on a bad bearer token; `/api/homeassistant/health`
serves the full capability set this integration consumes plus all four advertised endpoints; the
manifest action still wraps its payload as `result.device`; the Home Graph status, issues, sources
and pages routes return their documented shapes; `refinement/run` still returns the full `triage`
block; `conversation/cancel` answers `400` (input validation, not a 404). Mail and calendar answer
the same classifiable shapes the `1.20.0` pass confirmed: `email.send` and `email.draft.create`
answer `400 INVALID_INPUT`; `email.inbox.list` and `email.inbox.read` answer `501 NOT_INVOKABLE`;
`calendar.events.create` answers `400 INVALID_INPUT`; `calendar.events.get` and
`calendar.events.list` answer `400 CALENDAR_NOT_CONFIGURED`, never a `503 ws-call-overloaded`
routing fault reported as capacity.

Pytest passed in full: 257 passed, 1 skipped (`test_generated_client_sync.py`, which skips absent
a sibling `goodvibes-sdk` checkout, expected in this environment, the same skip every prior pass
has recorded). `python -m compileall`, the frontend JS syntax check, `frontend`'s `npm run check`
(built artifacts match source), and the release-metadata consistency check all passed.

The `1.20.0` pass (2026-07-30) closed a four-release drift: the integration still claimed `1.18.1`
while `1.19.0`, `1.19.1`, `1.19.2` and `1.20.0` had published. The entire `1.19.x` train was
missed. It re-vendored `custom_components/goodvibes/generated_client.py` byte-for-byte from the
published `1.20.0` package's Python artifact; the only diff from `1.18.1` is the contract version
label, so all 33 consumed methods, routes and types are unchanged across the whole span.

`scripts/validate-daemon-contract.mjs 1.20.0` passed every check against a daemon booted from the
published `1.20.0` SDK in an isolated home on an ephemeral loopback port: `/status` returns
`status: running` / `version: 1.20.0` and `401` on a bad bearer token; `/api/homeassistant/health`
serves the full capability set this integration consumes plus all four advertised endpoints; the
manifest action still wraps its payload as `result.device`; the Home Graph status, issues, sources
and pages routes return their documented shapes; `refinement/run` still returns the full `triage`
block; `conversation/cancel` answers `400` (input validation, not a 404). Mail and calendar answer
the same classifiable shapes the `1.18.1` pass first confirmed: `email.send` and
`email.draft.create` answer `400 INVALID_INPUT`; `email.inbox.list` and `email.inbox.read` answer
`501 NOT_INVOKABLE`; `calendar.events.create` answers `400 INVALID_INPUT`; `calendar.events.get`
and `calendar.events.list` answer `400 CALENDAR_NOT_CONFIGURED`, never a `503 ws-call-overloaded`
routing fault reported as capacity.

The SDK's `1.19.x`/`1.20.0` span added operator methods this integration does not consume:
`occasions.*` (proactive occasion/plan tracking: `occasions.list`, `.propose`, `.confirm`,
`.plans.*`, `.interview.*`, `.gifts`, `.sweep`, `.state`), `voice.wake.*` (wake-word model
provisioning and status), and several settings domains (`config.get`/`config.set`,
`checkin.config.*`, `mcp.config.*`, `security.settings`, `settings.snapshot`). None of them are in
the REST subset `generated_client.py` vendors (`channels.*`, `control.status`,
`homeassistant.homeGraph.*`, `tasks.*`, `email.*`, `calendar.events.*`), so there is no adaptation
required and nothing new for Home Assistant to surface yet, confirmed by the byte-for-byte
re-vendor above, not merely assumed from the changelog.

Pytest passed in full: 257 passed, 1 skipped (`test_generated_client_sync.py`, which skips absent a
sibling `goodvibes-sdk` checkout, expected in this environment, the same skip every prior pass has
recorded). `python -m compileall`, the frontend JS syntax check, `frontend`'s `npm run check`
(built artifacts match source), and the release-metadata consistency check all passed.

The `1.17.2` pass (2026-07-27) closed a five-release drift: the integration still claimed `1.15.0`
while `1.16.0`, `1.16.1`, `1.17.0`, `1.17.1` and `1.17.2` had published. It re-vendored
`custom_components/goodvibes/generated_client.py` byte-for-byte from the published `1.17.2`
package's Python artifact; the only diff from `1.15.0` is the contract version label, so all 33
consumed methods, routes and types are unchanged across the whole span.

The pass ran `scripts/validate-daemon-contract.mjs` (new this pass) against a daemon booted from
the published `1.17.2` SDK in an isolated home on an ephemeral loopback port, and every check
passed. Confirmed live: `/status` returns `status: running` / `version: 1.17.2` and `401` on a bad
bearer token; `/api/homeassistant/health` serves the full capability set this integration consumes
(`conversation-submit-wait`, `conversation-stream`, `conversation-cancel`, `stable-correlation`,
`isolated-remote-chat-session`, `remote-session-ttl`, `homeassistant-event-delivery`) plus all four
advertised endpoints; the manifest action still wraps its payload as `result.device`; the Home
Graph status, issues, sources and pages routes return their documented shapes; and
`refinement/run` still returns the full `triage` block (`ok`, `spaceId`, `configured`, `processed`,
`skipped`, `applied`, `reviewed`, `decisions`, `remaining`, `minConfidence`) the panel's automatic
triage depends on. `conversation/cancel` answers `400 "sessionId or known messageId is required."`
The route is alive and validating input, not returning a 404.

Nothing in the integration broke across the window. The daemon-side changes in it are additive or
internal from this integration's point of view:

- **`/status` gained a `cluster` block** (`enabled`, `role`, `nodeId`, `heldSurfaceCount`, `peers`,
  `transport`, …). The integration reads `status` and `version` off that response with `.get()` and
  has no strict schema over it, so the extra block is inert here.
- **Daemon-owned config tiers.** `config.set` now reports `persistedTo`, `tier` and `daemonOwned`.
  This integration does not call `config.set`, so it is unaffected, but the tier is what makes
  mail and calendar setup performed on any surface visible to all of them (see
  [mail-calendar.md](mail-calendar.md)).
- **Surface-scoped storage.** `ConfigManager` now *requires* a `surfaceRoot` when its paths are
  derived from `homeDir`/`workingDir`; constructing one without it raises. This is an SDK-embedder
  concern and does not touch this integration, which speaks only HTTP, but it did break the ad-hoc
  boot recipe used by earlier validation passes, which is one more reason that recipe is now a
  committed script rather than prose.
- **Conversation gate and cluster settings** did not change any route this integration calls.

The `1.15.0` pass (2026-07-26) re-vendored `custom_components/goodvibes/generated_client.py`
byte-for-byte from the published `1.15.0` package's Python artifact; the only diff from `1.12.1`
is the contract version label. This pass covers three SDK releases at once: the integration was
last validated at `1.12.1`, and `1.13.0`, `1.13.1` and `1.14.0` published in between, so the
whole span is accounted for here rather than only the newest release.

`1.15.0` does change the operator contract, but not the part this integration consumes: the
config-set response gained `persistedTo`, `tier` and `daemonOwned` alongside daemon-owned config
scope. The generated client covers only the REST subset Home Assistant calls, and `config.set` is
not one of the 33 consumed methods: the consumed set is `channels.*`, `control.status`,
`homeassistant.homeGraph.*` and `tasks.*`, so all 33 methods, routes and types are unchanged.
That is verified rather than assumed: the regenerated artifact differs from the vendored `1.12.1`
copy only in its version label.

The pass booted a daemon from the published `1.15.0` SDK in an isolated home (the same
`bootDaemon` recipe as earlier passes, ephemeral loopback port, stopped in a `finally` block),
confirmed the unauthenticated `/status` probe is refused (401), confirmed authenticated `/status`
reports `running` / `1.15.0`, and confirmed `/api/homeassistant/health` serves the full capability
set this integration consumes (`conversation-submit-wait`, `conversation-stream`,
`conversation-cancel`, `stable-correlation`, `isolated-remote-chat-session`, `remote-session-ttl`,
`homeassistant-event-delivery`).

The `1.12.1` pass (2026-07-25) re-vendored `custom_components/goodvibes/generated_client.py`
byte-for-byte from the published `1.12.1` package's Python artifact; the only diff from `1.12.0`
is the contract version label. `1.12.1`'s changes are daemon-internal recovery-lifecycle fixes
with the HTTP operator contract unchanged. The pass booted a daemon from the published `1.12.1`
SDK in an isolated home, confirmed the unauthenticated `/status` probe is refused (401),
confirmed authenticated `/status` reports `1.12.1`, and confirmed `/api/homeassistant/health`
serves the full capability set this integration consumes.

The `1.12.0` pass (2026-07-24) re-vendored `custom_components/goodvibes/generated_client.py`
byte-for-byte from the published `1.12.0` package's Python artifact; the only diff from `1.11.4`
is the contract version label. `1.12.0` introduces declare-once product storage surfaces, the
ask-then-retire recovery lifecycle, and a cross-process workspace-checkpoint lock, all internal
to the daemon host with the HTTP operator contract unchanged. The pass booted a daemon from the
published `1.12.0` SDK in an isolated home, confirmed the unauthenticated `/status` probe is
refused (401), confirmed authenticated `/status` reports `1.12.0`, and confirmed
`/api/homeassistant/health` serves the full capability set this integration consumes.

The `1.11.4` pass (2026-07-18) re-vendored `custom_components/goodvibes/generated_client.py`
byte-for-byte from the published `1.11.4` package's Python artifact; the only diff from `1.11.3`
is the contract version label. `1.11.4` hardens the SDK-internal secrets keyfile handling and
does not touch the operator contract, so all 33 consumed methods, routes, and types are
unchanged. The pass booted a daemon from the published `1.11.4` SDK (same isolated-home
`bootDaemon` recipe as the `1.11.3` pass) and probed the routes this integration reads directly:
`/status` returned `status: running`/`version: 1.11.4` and `401` on a bad bearer token;
`/api/homeassistant/health` capabilities include `conversation-stream` and `conversation-cancel`;
both home-graph routes returned `ok`. This repo's full pytest suite (208 tests) passed against
the re-vendored client.

The `1.11.3` pass (2026-07-17) re-vendored `custom_components/goodvibes/generated_client.py`
byte-for-byte from the published `1.11.3` package's Python artifact; the only diff from `1.11.2`
is the contract version label (`CONTRACT_VERSION = "1.11.3"`). `1.11.3` fixes SDK-internal
logging/publish behavior and adds a transcript-rendering export, none of which touches the
operator contract, so all 33 consumed methods, routes, and types are unchanged. The pass booted a
daemon from the published `1.11.3` SDK (`bootDaemon` from `@pellux/goodvibes-sdk/daemon`, isolated
home and working directories, ephemeral loopback port, stopped in a `finally` block) and probed
the routes this integration reads directly: `/status` returned `status: running`/`version: 1.11.3`
and `401` on a bad bearer token; `/api/homeassistant/health` capabilities include
`conversation-stream` and `conversation-cancel`; `/api/homeassistant/home-graph/status` returned
`ok` and `readiness`; `/api/homeassistant/home-graph/issues` returned `ok` with an issue list.
The conversation/stream/cancel deep exercise was not repeated. The contract those routes bind to
is byte-for-byte identical to the fully-exercised `1.10.1` pass. This repo's full pytest suite
(208 tests) passed against the re-vendored client.

The 2026-07-17 pass re-vendored `custom_components/goodvibes/generated_client.py` byte-for-byte
from the published `1.11.2` package's Python artifact; the only diff from `1.10.1` is the version
label itself (`Contract product version: 1.11.2`, `CONTRACT_VERSION = "1.11.2"`). The SDK's
`1.11.0`/`1.11.1`/`1.11.2` releases are release-engineering only (shared CI/CD toolchain + reusable
workflows) and did not touch the operator contract, so all 33 consumed methods, routes, and types
are unchanged. This pass also booted a daemon from the published `1.11.2` SDK (`bootDaemon` from
`@pellux/goodvibes-sdk/daemon`, isolated home and working directories, ephemeral loopback port,
stopped in a `finally` block) and probed the routes this integration reads directly: `/status`
returned `status`/`version: 1.11.2` and `401` on a bad bearer token; `/api/homeassistant/health`
capabilities include `conversation-stream` and `conversation-cancel`;
`/api/homeassistant/home-graph/status` returned `ok`, the graph counts, and `readiness`;
`/api/homeassistant/home-graph/issues` returned `ok`/`spaceId`/`issues`. The conversation/stream/
cancel deep exercise was not repeated this pass. The contract those routes bind to is
byte-for-byte identical to the fully-exercised `1.10.1` pass. This repo's full pytest suite passed
against the re-vendored client.

The 2026-07-16 pass re-vendored `custom_components/goodvibes/generated_client.py` byte-for-byte
from the published `1.10.1` package's own generated Python artifact
(`dist/contracts/artifacts/python/homeassistant_operator_client.py`, extracted from
`@pellux/goodvibes-sdk@1.10.1` on npm). The only diff from `1.10.0` is the version label itself
(`Contract product version: 1.10.1` and `CONTRACT_VERSION = "1.10.1"`); the operator contract's
REST subset this client depends on (33 methods) and all its route bindings and types are
byte-for-byte unchanged, so 1.10.1 (a patch release adding type aliases and export subpaths only)
did not touch the HA-consumed method set at all. This pass also booted a daemon from the published
`1.10.1` SDK (isolated home directory, isolated working directory, ephemeral loopback port, Home
Assistant surface enabled, composed via the SDK's own published `bootDaemon` factory from
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

## Response-shape validation

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

## Minimum expected daemon surface

The config flow validates:

- `GET /status`
- `GET /api/homeassistant/health`
- `POST /api/channels/actions/homeassistant/homeassistant-manifest`
- `GET /api/homeassistant/home-graph/status` when Home Graph is enabled

Assist uses:

- `POST /api/homeassistant/conversation/stream` (streamed), alongside
  `POST /api/homeassistant/conversation`.

Home Graph uses the daemon routes listed in [home-graph.md](home-graph.md#daemon-routes).

Mail and calendar use the daemon routes listed in [mail-calendar.md](mail-calendar.md). They are
**optional**: a daemon that does not serve them is a supported configuration, and the integration
reports that state honestly rather than failing setup. As of `1.18.0` the daemon serves `email.*`
and `calendar.*` itself (`invokable: true` in the operator contract); a fresh daemon with no
account connected answers `400` with a `*_NOT_CONFIGURED` code (or `501 NOT_INVOKABLE` for the
inbox-read routes) rather than `404`. This is verified, not assumed, by
`scripts/validate-daemon-contract.mjs`, which records the served/not-served status and the
response shape of each one on every run.

## Validation checklist

Steps 1 and 2 are now automated. Run them with:

```bash
bun scripts/validate-daemon-contract.mjs           # against npm latest
bun scripts/validate-daemon-contract.mjs 1.20.0    # against a pinned release
```

That covers the version coherence check, the vendored-artifact diff, and every route and response
shape listed above, against a real daemon it boots and stops itself. The remaining steps need a
Home Assistant instance and stay manual.

After a daemon SDK update, and after refreshing `const.SDK_VALIDATED_VERSION`:

1. Check `GET /status`. *(automated)*
2. Check `GET /api/homeassistant/health`. *(automated)*
3. Restart Home Assistant after the daemon is healthy.
4. Open the `GoodVibes Home` panel.
5. Run `goodvibes.sync_home_graph`.
6. Ask a source-backed Home Graph question.
7. Load generated pages.
8. Load the visual map.
9. Run `goodvibes.home_graph_reindex` if old uploads need reparsing or semantic enrichment.
10. Test Assist through a Home Assistant Assist pipeline.

## Contract rules

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
