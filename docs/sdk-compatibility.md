# SDK Compatibility

This integration currently targets `@pellux/goodvibes-sdk@0.34.0`.

The Home Assistant integration is intentionally a thin client over daemon-owned APIs. SDK upgrades usually require validation against daemon routes and response shapes, not local Home Assistant graph logic.

## Current Target

`@pellux/goodvibes-sdk@0.34.0` is the current daemon/runtime compatibility target for integration version `0.5.72`.

Validation focus:

- Companion-chat Assist finalization fix from `0.33.24`.
- WRFC compound-chain and auto-commit runtime fixes from `0.33.25` through `0.33.26`.
- Runtime MCP config support from `0.33.27`.
- Auto-compaction and exec alias fixes from `0.33.28`.
- Project-mode prompt classification fixes from `0.33.29`.
- QEMU JavaScript-family REPL command fixes from `0.33.30`.
- Daemon/runtime fixes across `0.33.31` through `0.33.38`.
- Additive operator method contracts from `0.34.0` (new `channels.*` inbox/routing/drafts methods plus new `email.*` and `calendar.*` namespaces) and transitive build/test dependency security advisory cleanup, with no breaking changes to existing methods.
- No expected Home Assistant panel contract change from the SDK update.

After upgrading or restarting the daemon SDK during live validation, restart Home Assistant after the daemon reports healthy.

## Response-shape Validation

The five daemon response shapes the integration reads most directly were checked against the current GoodVibes SDK daemon router source and confirmed intact:

- `GET /status` returns `status` and `version`, and returns HTTP `401` when the bearer token is rejected. The daemon status sensor and the config flow read both fields.
- `GET /api/homeassistant/home-graph/status` returns `ok` plus the graph counts (`sourceCount`, `nodeCount`, `edgeCount`, `issueCount`) and a `readiness` block. The Home Graph status sensor treats `ok: true` as ready; the endpoint has no top-level `status` field, so the sensor's `status` lookup falls back to the `ok` check, which is the intended behavior.
- `GET /api/homeassistant/home-graph/issues` returns `ok`, `spaceId`, and an `issues` list. The issues sensor counts the list length.
- `POST /api/homeassistant/conversation` returns `status`, `mode`, `sessionId`, `messageId`, and, on a completed turn, an `assistant` object with `speechText` and `text`. The Assist agent reads all of these. The response has no `agentId` field; the integration treats that as optional and skips it when absent.
- `POST /api/channels/actions/homeassistant/homeassistant-manifest` wraps its result as `{ actionId, surface, result: { device: { identifiers, manufacturer, model, name }, ... } }`. The integration unwraps `result` and reads the `device` fields. The device object has no `swVersion`; the integration falls back to the daemon status `version`, which is the intended behavior.

No response-shape drift that breaks the integration was found. These are also encoded as assertions in the test suite so a future SDK change that renames one of these fields is caught in CI.

Version-label note: this validation read the GoodVibes SDK router source directly, and that source's package manifest reported version `1.2.0`, while this integration tracks its daemon target as `0.34.0`. The routes and response shapes matched regardless of the label, but the two version schemes should be reconciled so the "current target" number is unambiguous.

## Minimum Expected Daemon Surface

The config flow validates:

- `GET /status`
- `GET /api/homeassistant/health`
- `POST /api/channels/actions/homeassistant/homeassistant-manifest`
- `GET /api/homeassistant/home-graph/status` when Home Graph is enabled

Assist uses:

- `POST /api/homeassistant/conversation`

Home Graph uses the daemon routes listed in [home-graph.md](home-graph.md#daemon-routes).

## Compatibility Notes

| SDK version | Integration concern |
| --- | --- |
| `0.34.0` | Current target (`0.34.0`). Additive `channels.*` / `email.*` / `calendar.*` operator method contracts and transitive dependency security cleanup. No breaking changes to existing methods and no Home Assistant panel contract change expected. |
| `0.33.31` through `0.33.38` | Daemon/runtime compatibility validation. No Home Assistant panel contract change expected. |
| `0.33.30` | Runtime compatibility validation for QEMU JavaScript-family REPL command fixes. No Home Assistant panel contract change expected. |
| `0.33.29` | Project-mode prompt classification fixes. No Home Assistant panel contract change expected. |
| `0.33.28` | Auto-compaction and exec alias fixes. No Home Assistant panel contract change expected. |
| `0.33.27` | Runtime MCP config support. No Home Assistant panel contract change expected. |
| `0.33.25` through `0.33.26` | WRFC compound-chain and auto-commit runtime fixes. No Home Assistant panel contract change expected. |
| `0.33.24` | Companion-chat tool-loop exhaustion finalizes Assist turns instead of returning a daemon HTTP `500` when repeated tool calls do not produce a final answer. |
| `0.28.x` | Home Graph Ask, generated pages, map filters, reindex, reset, refinement, source repair, and semantic quality behavior matured across these releases. The integration should remain thin and render SDK-owned response fields directly. |
| `0.27.x` | Earlier Home Graph semantic filtering, map, source, and generated page behavior. Upgrade to the current target before debugging current Home Assistant panel behavior. |

## Validation Checklist

After a daemon SDK update:

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

- Keep graph storage, search, page generation, packets, artifacts, answer synthesis, and map layout daemon-owned.
- Render daemon-provided fields directly instead of inferring graph linkage locally.
- Preserve SDK fields such as `answer.refinement`, `answer.refinementTaskIds`, `facts`, `gaps`, `linkedObjects`, `sources`, `subject`, `subjectIds`, `linkedObjectIds`, and `targetHints`.
- Send map filters to the daemon and display returned SVG/facets.
- Use the SDK reset route for destructive Home Graph reset. Do not implement reset through local database edits.
- Use export/import only for backup and transfer, not reset.
