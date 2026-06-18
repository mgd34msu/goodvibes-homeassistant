# SDK Compatibility

This integration currently targets `@pellux/goodvibes-sdk@0.33.38`.

The Home Assistant integration is intentionally a thin client over daemon-owned APIs. SDK upgrades usually require validation against daemon routes and response shapes, not local Home Assistant graph logic.

## Current Target

`@pellux/goodvibes-sdk@0.33.38` is the current daemon/runtime compatibility target for integration version `0.5.71`.

Validation focus:

- Companion-chat Assist finalization fix from `0.33.24`.
- WRFC compound-chain and auto-commit runtime fixes from `0.33.25` through `0.33.26`.
- Runtime MCP config support from `0.33.27`.
- Auto-compaction and exec alias fixes from `0.33.28`.
- Project-mode prompt classification fixes from `0.33.29`.
- QEMU JavaScript-family REPL command fixes from `0.33.30`.
- Daemon/runtime fixes across `0.33.31` through `0.33.38`.
- No expected Home Assistant panel contract change from the SDK update.

After upgrading or restarting the daemon SDK during live validation, restart Home Assistant after the daemon reports healthy.

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
| `0.33.31` through `0.33.38` | Current target (`0.33.38`). Daemon/runtime compatibility validation. No Home Assistant panel contract change expected. |
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
