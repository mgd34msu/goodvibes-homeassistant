# Home Graph triage engine — capability comparison

**Status: the port scoped below has landed.** The SDK now owns the triage loop as a mode of
`refinement/run` (decision record `2026-07-07-home-graph-issue-triage.md` in the SDK repo, `1.3.0`).
`_async_triage_home_graph_issues` in `frontend.py` is now a thin proxy onto that call; every piece
listed in "genuine delta" below (the LLM loop, the confidence threshold, the decision cache) has
been deleted from this integration and lives in the daemon instead. This document is kept for the
historical comparison it recorded, not as a description of current behavior — see
`docs/home-graph.md` (Review section) and `docs/sdk-compatibility.md` for the current contract.

This document compares the LLM triage engine that used to live in this integration
(`custom_components/goodvibes/frontend.py`) against the Home Graph machinery the GoodVibes SDK
already ships (validated against `@pellux/goodvibes-sdk@1.2.0`). Its purpose is to scope a separate
follow-up: moving the genuinely SDK-owned behavior into the SDK's own Home Graph refinement, where
every consumer (this integration, the terminal UI, the web UI) can share one triage policy.

**This is planning only. Nothing here is a change to make now.** The Python triage engine keeps
working and stays in place until an SDK replacement lands and is gated behind a daemon capability
check so older daemons still work.

## What the Python triage engine does today

Entry point `_async_triage_home_graph_issues` (`frontend.py:913`), reached from the panel's
`triage_issues` action. In order, it:

1. Lists open Home Graph issues and browses graph nodes from the daemon
   (`home_graph_issues` + `home_graph_browse`).
2. Builds a compact per-issue record joining the issue (code, severity, status, message) with its
   node (kind, title, summary, aliases, manufacturer, model) and its Home Assistant metadata
   (entityId, deviceId, areaId, integrationId) — `_triage_issue_record` (`frontend.py:608`).
3. Sends the records to the daemon conversation endpoint in chunks of 25 (`TRIAGE_CHUNK_SIZE`,
   `frontend.py:90`), wrapped in an LLM instruction (`_triage_prompt`, `frontend.py:683`) asking the
   model to classify each issue as `reject` (clearly not applicable/incorrect, safe to dismiss) or
   `review` (uncertain, needs a human), returning strict JSON
   `{"decisions":[{"issueId","action","category","confidence","reason","fact"}]}`.
4. Parses and normalizes the decisions (`_parse_triage_decisions`, `frontend.py:734`).
5. Auto-applies `reject` decisions at or above `0.85` confidence (`TRIAGE_CONFIDENCE_THRESHOLD`,
   `frontend.py:1011`) by POSTing to `facts/review` with a "semantic review value" that carries
   category/confidence/reason/source and, for known codes, a derived fact
   (`_semantic_review_value`, `frontend.py:1057`).
6. Persists a per-issue fingerprint cache so unchanged open issues are not re-triaged
   (`_triage_issue_fingerprint`, `frontend.py:880`, plus the Store-backed cache helpers).

## 1. Redundant — the SDK already does this

These parts of the Python engine duplicate behavior the SDK already ships. Porting the delta (§2)
into the SDK lets the integration drop them.

- **Issue generation with built-in applicability filtering.** The SDK's
  `refreshHomeGraphQualityIssues` (`knowledge/home-graph/quality.ts:107-128`) raises exactly the two
  codes the Python engine special-cases — `homegraph.device.unknown_battery` and
  `homegraph.device.missing_manual`. Its `shouldRequireBatteryType` / `shouldRequireManual`
  (`quality.ts:162-194`) and `isSoftwareOrInfrastructure` (`quality.ts:196-207`), backed by the
  `EXCLUDED_SOFTWARE_TERMS` / `EXCLUDED_INFRASTRUCTURE_TERMS` / `EXCLUDED_MAINS_TERMS` lists
  (`quality.ts:8-56`), already exclude software, automations, scenes, integrations, sun/weather, and
  mains-powered devices — the same judgment the Python prompt asks the model to make, applied
  deterministically at issue-creation time.
- **The reject → derive-fact mapping.** `deriveIssueFacts` (`knowledge/home-graph/review.ts:154-178`)
  already produces `{batteryPowered:false, batteryType:"none"}` for an `unknown_battery`
  reject/resolve and `{manualRequired:false}` for a `missing_manual` reject — functionally identical
  to the Python engine's `_semantic_review_value` special-casing.
- **The `facts/review` target.** `POST /api/homeassistant/home-graph/facts/review` →
  `reviewHomeGraphFact` (`daemon/http/home-graph-routes.ts:172-174`, `review.ts:21-127`) already
  accepts `action: accept|reject|resolve|edit|forget` plus a `value`; `normalizeReviewFacts`
  (`review.ts:180-200`) allowlists exactly the fact fields the Python "fact" object carries, and
  `readCategory` (`review.ts:232-234`) treats `not_applicable` specially. The Python auto-apply POST
  has a 1:1 target already shipped. Note: `confidence`/`reason`/`source` are accepted but stored
  inertly under `metadata.review.value` (`review.ts:202-209`) — the SDK does not act on them.
- **A per-issue fingerprint dedupe.** `subjectFingerprint` + `isSuppressedGeneratedIssue`
  (`quality.ts:148-160, 209-229`) already hash an issue's identity and skip re-raising an unchanged,
  resolved issue. This overlaps the Python fingerprint cache — but note the SDK's version gates
  re-**creation** of an issue, whereas the Python cache gates re-**triage** of an open one (see §2).
- **The full HTTP surface.** `GET /issues`, `GET /browse` (returns `{nodes, edges, sources, issues}`,
  `knowledge/home-graph/inventory.ts:21-44`), `POST /facts/review`, and the `/refinement/*` routes
  all exist and are stable — the integration is calling real endpoints, nothing to add for
  connectivity.
- **A confidence-gated auto-apply precedent.** `WebGapRepairOptions.minConfidence` (default 70) in
  `knowledge/semantic/gap-repair.ts` gates whether a discovered web source is auto-ingested — the
  same "trust above a threshold" idiom as the Python `0.85` gate, though applied to a different
  decision in a different subsystem.

## 2. Genuine delta — must be ported into the SDK's Home Graph refinement

None of the following exists in the SDK today; this is the real net-new behavior a follow-up would
build into the SDK's Home Graph refinement engine.

- **An LLM-driven issue-triage loop.** The SDK has no code that batches open `homegraph.device.*`
  issues, prompts an LLM to classify each as reject/review, and parses back
  `{decisions:[{issueId,action,category,confidence,reason,fact}]}`. The two things that look adjacent
  are not it: `quality.ts` issue generation is pure deterministic heuristics (no LLM), and the
  "refinement" / self-improvement system (`knowledge/semantic/self-improvement*.ts`) operates on
  `knowledge_gap` nodes — missing spec/feature info filled by web search — not on the device quality
  issues; its `classifyGap` (`self-improvement-gap-context.ts:104-126`) is rule-based and never
  touches issue records. The natural home for the port is a new function alongside
  `quality.ts`/`review.ts`, or a new mode of the refinement engine, that lists open issues, batches
  them, prompts through the existing `KnowledgeSemanticLlm` plumbing (as `semantic/enrichment.ts` and
  `semantic/answer-llm.ts` do), and calls `reviewHomeGraphFact` for accepted decisions.
- **A confidence threshold on triage output.** `reviewFact` applies whatever action/value it is
  handed; there is no `0.85`-style auto-apply gate for issues. The `gap-repair.ts` `minConfidence`
  pattern is a good template, but it gates a different decision and lives in a different subsystem.
- **A triage-decision cache.** The SDK has generation-side fingerprint dedupe only. "We already
  triaged this open issue and decided X, skip until it changes" — the Python cache's actual
  guarantee — has no SDK equivalent and would move with the loop.
- **An extensible issue-code → applicability-rule framework.** The SDK's inclusion/exclusion logic is
  hardcoded to the two codes that exist today. Generalizing beyond `unknown_battery` /
  `missing_manual` is new design work, not adaptation of an existing framework.

## 3. Integration glue — stays in the integration regardless

These are inherently Home-Assistant-surface concerns and stay local even after the port.

- **Reading Home Assistant registries** to produce `entityId` / `deviceId` / `areaId`. The SDK only
  stores what was synced into `node.metadata.homeAssistant` (`knowledge/home-graph/helpers.ts:152-155,
  290-293, 334-337`); it has no registry of its own to consult.
- **Calling `GET /issues` + `GET /browse` and assembling the per-issue record** that joins node
  fields with Home Assistant metadata — an HTTP client loop over SDK-owned endpoints.
- **Driving the triage prompt against the conversation endpoint** — integration-owned only until the
  loop in §2 is ported; once it is, this glue shrinks to "call `refinement/run`" and the batching and
  prompt move into the SDK.
- **The decision cache** stays outside the SDK for exactly as long as the triage prompt itself does.

## Follow-up shape

The SDK-side port is a separate follow-up work item, not part of this change. A safe sequence:

1. Build the LLM issue-triage loop (§2) inside the SDK's Home Graph refinement, reusing the existing
   issue generation, `deriveIssueFacts`, `reviewHomeGraphFact`, and semantic-LLM plumbing (§1).
2. Expose it behind a daemon capability flag so older daemons that lack it still work.
3. Switch the integration's `triage_issues` panel action to call the daemon capability when present,
   keeping the local Python engine as the fallback.
4. Retire the local engine (the §1 duplication and the §2 logic) only once the daemon capability is
   the default and the fallback is no longer needed.
