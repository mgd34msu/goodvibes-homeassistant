# Changelog

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
