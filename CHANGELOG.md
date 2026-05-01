# Changelog

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
