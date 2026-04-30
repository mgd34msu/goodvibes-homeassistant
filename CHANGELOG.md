# Changelog

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
