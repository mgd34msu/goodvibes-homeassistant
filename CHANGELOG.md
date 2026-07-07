# Changelog

## Unreleased

## 0.6.1 - 2026-07-07

- Validate against `@pellux/goodvibes-sdk` 1.4.0. With a daemon at 1.4.0+
  (GoodVibes TUI 1.11.0+), cancelling an in-flight Assist reply now stops just
  that reply — the conversation session stays open, so the next utterance
  keeps its context. (Older daemons closed the whole session on cancel; the
  integration's own code is unchanged either way.)

- Add the integration's first test suite (pytest with pytest-homeassistant-custom-component) covering the config flow, the daemon client and its error taxonomy, the panel upload reader, and the config-entry lifecycle, plus a CI job that runs it on Python 3.13.
- Move the panel upload's temp-file writes and the client's upload read-back off the event loop so a large upload no longer blocks Home Assistant on disk I/O.
- Refuse a panel upload larger than 512 MiB before buffering it to local disk, with an HTTP 413 response that names the limit.
- Replace substring-based daemon-error classification with a typed client exception hierarchy (unavailable, unauthorized, surface-missing, daemon-error); the config flow now selects its error by type.
- Scope the Home Graph startup auto-sync task to the config entry so unload and reload cancel it instead of leaving it running.
- Collapse the panel asset version knob onto `INTEGRATION_VERSION` so there is a single integration version.
- Record the response-shape validation against the current SDK daemon router in `docs/sdk-compatibility.md`.

## 0.6.0

- Assist conversations stream incrementally: the daemon now emits partial responses as they are generated, and the integration renders them as they arrive instead of blocking on the full reply.
- Issue triage now runs server-side in the GoodVibes daemon (model-routed, confidence-gated, decision-cached); the integration's local triage engine is removed. Older daemons without server-side triage get an honest "not supported" outcome.
- Startup and refresh are faster: daemon reads now run concurrently through a coordinator instead of one at a time.
- Internal restructure: payload building unified into one module, the 26 services extracted from the setup file into a services module, and a test suite (92 tests) with a CI test job now guards the integration.
- Fixed: uploads no longer block Home Assistant's event loop; oversized uploads are refused with the limit stated; daemon errors carry typed reasons (unreachable / unauthorized / surface missing); the background sync task is scoped to the config entry across reloads.
- The integration targets the latest GoodVibes SDK, validated against 1.3.1; the MIT license file is included (required by the current HACS validation).

## 0.5.72

- Target `@pellux/goodvibes-sdk@0.34.0`.
- Document the `0.34.0` validation focus: additive operator method contracts (new `channels.*` inbox/routing/drafts methods plus new `email.*` and `calendar.*` namespaces) and transitive build/test dependency security advisory cleanup, with no breaking changes to existing methods and no expected Home Assistant panel contract change.
- Split the README into a shorter setup guide plus focused Home Graph, service, troubleshooting, and SDK compatibility documentation under `docs/`.
- Add development/release, security/credentials, and known-limits documentation.
- Bump first-party GitHub Actions to Node 24-compatible major versions and declare the integration as config-entry-only for Hassfest.

## 0.5.71

- Target `@pellux/goodvibes-sdk@0.33.38`.
- Document the `0.33.38` validation focus: latest daemon/runtime compatibility across the `0.33.31` through `0.33.38` releases, with no expected Home Assistant panel contract change.

## 0.5.70

- Target `@pellux/goodvibes-sdk@0.33.30`.
- Document the `0.33.30` validation focus: latest daemon/runtime compatibility, including runtime MCP config, auto-compaction and exec alias fixes, project-mode prompt classification fixes, QEMU JavaScript-family REPL command fixes, and no expected Home Assistant panel contract change.

## 0.5.69

- Target `@pellux/goodvibes-sdk@0.33.26`.
- Document the `0.33.26` validation focus: latest daemon/runtime compatibility, including WRFC compound-chain and auto-commit fixes, with no expected Home Assistant panel contract change.

## 0.5.68

- Target `@pellux/goodvibes-sdk@0.33.24`.
- Document the `0.33.24` validation focus: companion-chat tool-loop exhaustion now finalizes Assist turns instead of returning a daemon HTTP 500 when repeated tool calls do not produce a final answer.

## 0.5.67

- Mask daemon bearer token and Home Assistant webhook secret fields in the config flow with Home Assistant password selectors.
- Document credential handling more explicitly: this integration does not store daemon credentials in `/tmp`; the daemon token is currently stored by Home Assistant in the config entry, GoodVibes `goodvibes://` secret references remain daemon-side config values, and the current GoodVibes-native token source is the daemon companion/operator pairing token until the SDK exposes a first-class Home Assistant scoped-token exchange.
- Use Home Assistant's thread-safe task scheduling for the startup Home Graph auto-sync callback.
- Keep Home Graph issues/sources sensor attributes recorder-safe by exposing counts plus a compact sample instead of storing the full daemon payload in entity state.

## 0.5.66

- Target `@pellux/goodvibes-sdk@0.33.4`.
- Document the `0.33.4` validation focus: daemon/runtime contract compatibility, strict public `remote.snapshot` shape, `/api/remote` schema cleanup, persisted shared-session normalization during daemon startup, and no expected Home Assistant panel contract changes.

## 0.5.65

- Target `@pellux/goodvibes-sdk@0.28.22`.
- Document the `0.28.22` validation focus: Ask-to-pages propagation, persisted source-to-fact and fact-to-Home-Assistant-device links before page regeneration, official source and canonical fact rendering on generated device passports, preservation of legitimate specs such as `2 x 10W`, and removal of stale `0 source(s)` and manual/source open questions when source-backed evidence exists.

## 0.5.64

- Target `@pellux/goodvibes-sdk@0.28.21`.
- Document the `0.28.21` validation focus: structured `answer.refinement` metadata, preserved answer-gap IDs, source-backed foreground repair completion, title/URL-only promotion blocking, verified repair tasks only after usable subject-linked facts exist, generated-page source collection through promoted fact links, stale missing-source suppression when evidence exists, base Ask parity, and clean LG page fact/source enrichment.

## 0.5.63

- Target `@pellux/goodvibes-sdk@0.28.20`.
- Document the `0.28.20` validation focus: initial Home Graph Ask waiting for overlapping same-gap repair and re-answering from repaired evidence, follow-up/base/concrete Ask parity, official LG/vendor source preference, real LG Home Assistant linked object scoping, top-level fact linkage fields, generated-page canonical fact dedupe, removal of table debris/direct-comparison/raw-evidence noise, preservation of legitimate specs such as `2 x 10W` speakers, map contract sanity, and daemon responsiveness.

## 0.5.62

- Target `@pellux/goodvibes-sdk@0.28.19`.
- Document the `0.28.19` validation focus: clean-space reset/sync/reindex, Home Graph and base knowledge Ask quality, official/vendor source preference, clean synthesized prose without routing fragments, top-level fact linkage, low-value fragment filtering, canonical typed generated pages, map/filter edges, and coalesced refinement contracts.

## 0.5.61

- Use SDK-provided Home Graph page relationship metadata in the Pages reader: `subject`, `target`, `neighbors`, and `relatedPages` now drive page navigation before markdown-derived fallback links.

## 0.5.60

- Target `@pellux/goodvibes-sdk@0.28.18`.
- Document the `0.28.18` validation focus: clean-space reset/sync/reindex/refinement, LG TV Home Graph and base knowledge Ask quality, exact linked Home Assistant object scoping, fact subject linkage fields, SDK-provided page subject/target/neighbor metadata, source/fact enriched pages, map filters/edges/facets, and task retry metadata.

## 0.5.59

- Add internal navigation to generated Home Graph pages: room/device markdown rows now link to matching generated pages when available and fall back to scoped map/search links for missing pages, models, areas, integrations, entities, and device IDs.
- Add a linked-pages and graph-context section to the Pages reader so Home Graph pages behave more like navigable wiki pages.

## 0.5.58

- Target `@pellux/goodvibes-sdk@0.28.17`.
- Document the `0.28.17` validation focus: reset artifact clearing, sync/reindex accounting, effective refinement limits, LG TV Ask source/fact quality, generated page structure, nested and top-level map filters, task retry lifecycle, and concrete linked object scoping.
- Change the GoodVibes Home Pages tab into a generated page browser and wiki-style reader, with raw maintenance controls moved behind collapsed sections.

## 0.5.57

- Target `@pellux/goodvibes-sdk@0.28.16`.
- Document the `0.28.16` validation focus: bounded foreground Ask repair for weak Home Assistant object answers, official/vendor already-indexed source reuse, typed subject-linked fact promotion, deferred-not-closed behavior when accepted sources produce no usable facts, coalesced refinement limit accounting, pages route reliability, and Home Assistant map filter behavior.

## 0.5.56

- Target `@pellux/goodvibes-sdk@0.28.15`.
- Document the `0.28.15` validation focus: daemon status responsiveness, Home Assistant sync return timing with foreground page caps, reset dry-run/destructive reset behavior, changed-only reindex accounting, Home Graph Ask and base knowledge Ask quality for the LG TV feature/spec query, synthesized prose versus raw snippets, official/vendor source preference, typed subject-linked repair facts, real Home Assistant linked objects, refinement run limit accounting, top-level `nextRepairAttemptAt`, generated page/passport cleanliness, map edge/self-loop/facet integrity, and panel status/progress compatibility.

## 0.5.55

- Target `@pellux/goodvibes-sdk@0.28.14`.
- Document the `0.28.14` validation focus: bounded refinement/run deadlines, synthesized Ask answers from usable sources/facts, official/vendor source preference, retryable/deferred repair task lifecycle with `nextRepairAttemptAt`, typed subject-linked facts from repaired evidence, bounded Home Assistant sync/page generation through `pageAutomation.maxRunMs`, already-indexed accepted sources counting as repair evidence, and matching base `knowledgeSpaceId: "homeassistant"` Ask behavior.

## 0.5.54

- Target `@pellux/goodvibes-sdk@0.28.13`.
- Document the `0.28.13` validation focus: bounded Home Graph Ask responses, refinement task IDs, background targeted source repair, LG TV feature/spec gap closure, scoped sources/facts/linked objects, and clean reset/sync/reindex/base-ask/pages/map/tasks/readiness timings.

## 0.5.53

- Target `@pellux/goodvibes-sdk@0.28.12`.
- Document the `0.28.12` validation focus: clean-space reset/sync/reindex/ask/pages/map, Home Assistant sync return behavior, Home Graph readiness/refinement tasks, base knowledge `knowledgeSpaceId: "homeassistant"` routing, and UI contract compatibility.
- Note that Home Assistant should be restarted after daemon SDK restarts during live validation so the integration reconnects cleanly.

## 0.5.52

- Target `@pellux/goodvibes-sdk@0.28.11`.
- Add Home Graph reset preview support through `dry_run`/`dryRun`, so the panel and service can call the SDK reset route non-destructively before requiring typed `RESET` for deletion.
- Document SDK `0.28.11` validation focus: reset dry-run previews, clean-space sync/reindex/ask/pages/map, bounded feature/spec repair during Ask, concrete Home Assistant knowledge-space repair task placement, and map self-loop filtering.

## 0.5.51

- Target `@pellux/goodvibes-sdk@0.28.10`.
- Add thin-client support for the SDK-owned admin reset route `POST /api/homeassistant/home-graph/reset` through the GoodVibes Home panel websocket bridge and the `goodvibes.home_graph_reset` service.
- Require typed `RESET` confirmation before calling the dangerous reset route, and keep export/import documented as backup/transfer only, not reset.
- Document the clean-space rebuild flow: export diagnostics, reset the target `homeassistant:<installationId>` space through the SDK route, sync the real Home Assistant snapshot, reingest or relink uploads, then run reindex/refinement/page generation before retesting.
- Stop reading Home Assistant's deprecated `device.suggested_area` field while building Home Graph snapshots.

## 0.5.50

- Target `@pellux/goodvibes-sdk@0.28.9`.
- Refine the Home Graph map panel after live use: add an Automations drilldown, add local filter search, avoid rendering a useless graph when the daemon returns no edges, and keep raw technical device/entity IDs out of the primary filter list unless they have a human label.
- Keep current graph contents out of source-quality conclusions until the SDK-owned Home Graph reset route lands; the current space is likely contaminated by earlier ingest/link/page behavior.

## 0.5.49

- Target `@pellux/goodvibes-sdk@0.28.9`.
- Improve the Home Graph map panel: use a quieter default graph, keep filters in a dedicated drilldown sidebar, hide unlabeled raw technical IDs from primary chip lists, and prefer human labels when the daemon returns matching map node or edge metadata.
- Keep the optional `coalesced` reindex field visible in operation summaries and retest Home Graph Ask, base knowledge Ask, pages, map edges, and reindex responsiveness against the live daemon after TUI confirms the daemon update.

## 0.5.48

- Target `@pellux/goodvibes-sdk@0.28.8`.
- Document SDK `0.28.8` Home Graph behavior: no panel contract change is expected except optional `coalesced` in reindex responses.
- Surface the optional reindex `coalesced` flag in the panel operation summary.
- Retest changed-only reindex, repeated reindex, Home Graph Ask, base knowledge Ask with `knowledgeSpaceId: "homeassistant"`, generated pages, and map filters against the live daemon after TUI version confirmation.

## 0.5.47

- Target `@pellux/goodvibes-sdk@0.28.7`.
- Document SDK `0.28.7` Home Graph behavior from static package review: generated pages should no longer render `knowledge.answer_gap`, `knowledge.semantic_gap`, or `knowledge.intrinsic_gap` records as page issues.
- Confirm the reindex contract remains compatible: changed-only reindex only auto-links reparsed sources, forced reindex still runs a broad source audit, and reindex keeps the `0.28.6` accounting fields.
- Confirm base knowledge Ask now treats `knowledgeSpaceId: "homeassistant"` as a Home Assistant namespace alias while the Home Graph panel contract remains unchanged.

## 0.5.46

- Target `@pellux/goodvibes-sdk@0.28.6`.
- Document SDK `0.28.6` Home Graph contract details from static package review: reindex returns `changedSourceCount`, `forcedSourceCount`, `skippedGeneratedPageArtifactCount`, `refreshedGeneratedPageCount`, `generatedPagePolicyVersion`, top-level `truncated`, and top-level `budgetExhausted`.
- Surface reindex accounting and generated-page refresh counts in the panel result summary instead of requiring raw JSON inspection.
- Improve Ask answer rendering so synthesized answer text stays primary, gaps/refinement work remain visible, and raw facts/sources/linked objects are compact supporting evidence.
- Add a Home Assistant `update` entity backed by GitHub releases with placeholder repository metadata for the upcoming public repo.
- Review pages/map/refinement contracts statically against the `0.28.6` package; endpoint shapes remain compatible with the existing thin-client panel.

## 0.5.45

- Target `@pellux/goodvibes-sdk@0.28.5`.
- Document SDK `0.28.5` Home Graph fixes: reindex should skip generated-page artifacts, enrich only changed or forced sources, refresh stale generated pages by page policy version, return `truncated` and `budgetExhausted`, and keep daemon health routes responsive.
- Document map and page quality expectations: filtered map edges should include endpoint ids and titles, readiness active counts should exclude detected backlog, and generated pages should filter additional SpeakerCompare, equal-power, Magic Remote, and manual boilerplate text.
- Keep the GoodVibes Home panel contract unchanged while retesting status, refinement, reindex, Ask, pages, and map against the updated daemon.

## 0.5.44

- Target `@pellux/goodvibes-sdk@0.28.4`.
- Document SDK `0.28.4` Home Graph fixes: reindex should stay bounded without wedging daemon health routes, filtered map responses should preserve graph edges, Ask sources should include source id and URL aliases, and generated pages should filter more SpeakerCompare and Magic Remote noise.
- Keep the GoodVibes Home panel contract unchanged while retesting status, refinement, reindex, Ask, pages, and map against the updated daemon.

## 0.5.43

- Target `@pellux/goodvibes-sdk@0.28.3`.
- Document SDK `0.28.3` Home Graph behavior: Ask responses repaired from web sources should keep real Home Assistant `linkedObjects`, overlapping repair requests should coalesce instead of stacking duplicate daemon work, and Home Graph status/refinement/reindex/ask/pages/map contracts remain daemon-owned.
- Keep the GoodVibes Home panel compatible with the SDK refinement run result fields introduced in `0.28.1` and capped in `0.28.2`.

## 0.5.42

- Target `@pellux/goodvibes-sdk@0.28.2`.
- Document SDK `0.28.2` Home Graph refinement behavior: broad refinement requests should cap foreground repair at an effective limit of 24, historical `No semantic gap repairer is configured` tasks should reopen or become retriable once the daemon wires a repairer, and Ask/reindex should remain responsive while repair continues asynchronously.
- Confirm the GoodVibes Home panel refinement summary remains compatible with the SDK `0.28.2` result fields.

## 0.5.41

- Target `@pellux/goodvibes-sdk@0.28.1`.
- Document SDK `0.28.1` Home Graph refinement behavior: Ask returns current evidence quickly with refinement task IDs when repair continues asynchronously, reindex queues repair work instead of blocking on foreground semantic repair, and broad refinement runs report `candidateGaps`, `processedGaps`, `requestedLimit`, `effectiveLimit`, `truncated`, and `budgetExhausted`.
- Surface the latest refinement run budget/result fields in the GoodVibes Home Refine tab so capped SDK work is visible without opening raw JSON.

## 0.5.40

- Target `@pellux/goodvibes-sdk@0.28.0`.
- Add thin-client support for SDK-owned Home Graph refinement tasks in the GoodVibes Home panel: readiness display, task listing, manual refinement run, targeted gap/source refinement, active-task cancellation, and Ask refinement task IDs.
- Document SDK `0.28.0` Home Graph behavior: readiness status, refinement lifecycle APIs, scoped generated pages, source-backed device page notes, map facets, and ask-time refinement task IDs remain daemon-owned.

## 0.5.39

- Target `@pellux/goodvibes-sdk@0.27.12`.
- Document SDK `0.27.12` Home Graph quality fixes: reindex quality issues should drop stale missing-manual and battery questions for linked LG TV manuals, generated pages should filter remote/accessory noise, and gap repair source metadata may include confidence scoring.
- Confirm the GoodVibes Home panel status/reindex/ask/pages/map calls remain compatible with the SDK `0.27.12` contract; no panel UI change was required.

## 0.5.38

- Target `@pellux/goodvibes-sdk@0.27.11`.
- Document SDK `0.27.11` Home Graph semantic quality fixes: self-improvement skip counts are now gap-specific, and Magic Remote/Bluetooth accessory compatibility is filtered from feature/spec facts, pages, and answers unless the user asks for remote or accessory details.
- Confirm the GoodVibes Home panel status/reindex/ask/pages/map calls remain compatible with the SDK `0.27.11` contract; no panel UI change was required.

## 0.5.37

- Target `@pellux/goodvibes-sdk@0.27.10`.
- Document SDK `0.27.10` Home Graph semantic self-improvement support: Home Graph now advertises `semantic-self-improvement`, and reindex semantic output may include `selfImprovement`.
- Confirm the GoodVibes Home panel sync/reindex/ask/pages/map calls remain compatible with the SDK `0.27.10` contract; no panel UI change was required.

## 0.5.36

- Target `@pellux/goodvibes-sdk@0.27.9`.
- Document SDK `0.27.9` Home Graph behavior: semantic answer synthesis is prioritized before background enrichment, and additional low-value manual boilerplate is filtered daemon-side.
- Confirm the GoodVibes Home panel ask/pages/map/reindex calls remain compatible with the SDK `0.27.9` contract; no panel UI change was required.

## 0.5.35

- Target `@pellux/goodvibes-sdk@0.27.8`.
- Document SDK `0.27.8` shared semantic quality filtering for feature/spec answers and generated Home Graph pages: truncated deterministic fragments, cable snippets, feature/spec-change boilerplate, remote control noise, remote battery-low notes, dry-cloth cleaning notes, and generic service/repair/customer-service boilerplate are filtered daemon-side.
- Confirm the GoodVibes Home panel ask/pages/map rendering remains compatible with the SDK `0.27.8` contract; no panel UI change was required.

## 0.5.34

- Target `@pellux/goodvibes-sdk@0.27.7`.
- Document SDK `0.27.7` Home Graph behavior: `linkedObjects` should contain real Home Assistant graph objects only, semantic fact/wiki/gap nodes stay in `facts`/`gaps`, weak manual fragments are filtered from feature/spec answers and generated pages, and Ask no longer waits synchronously for enrichment before provider-backed answer synthesis.
- Confirm the GoodVibes Home panel ask/pages/map rendering remains compatible with the SDK `0.27.7` contract; no panel UI change was required.

## 0.5.33

- Target `@pellux/goodvibes-sdk@0.27.6`.
- Document SDK `0.27.6` Home Graph behavior: object-scoped Ask should stop including unrelated broad sources, generated semantic pages/facts no longer become Home Assistant object anchors, stale deterministic facts are hidden, deterministic enrichment can be upgraded by provider-backed LLM during ask/reindex, and feature/spec answers filter low-value manual boilerplate.
- Confirm the existing GoodVibes Home panel sync/reindex/pages/ask/map calls remain compatible with the SDK `0.27.6` contract; no panel UI change was required.

## 0.5.32

- Target `@pellux/goodvibes-sdk@0.27.5`.
- Document SDK `0.27.5` Home Graph Ask behavior: strict semantic candidates after object-scoped search, query-intent filtering for deterministic facts, bounded provider-backed semantic calls, and bounded broad reindex LLM budget.
- Confirm the existing GoodVibes Home panel ask/reindex/pages calls match the SDK `0.27.5` contract; no local PDF parsing, ranking, page generation, or answer synthesis was added.

## 0.5.31

- Target `@pellux/goodvibes-sdk@0.27.4`.
- Render semantic Home Graph Ask fields from the SDK: synthesized answer state, facts, gaps, sources, and linked objects.
- Rename the panel reindex action to `Reindex uploads` and document SDK-owned semantic reindex/enrichment counts.

## 0.5.30

- Target `@pellux/goodvibes-sdk@0.27.3`.
- Add thin-client support for `GET /api/homeassistant/home-graph/pages` with markdown rendering in the GoodVibes Home panel.
- Document SDK `0.27.3` Home Graph repair behavior: reindex reparses existing uploaded PDFs, repairs weak/binary extraction, auto-links manuals to Home Assistant graph nodes, and regenerates generated pages with source-backed content.
