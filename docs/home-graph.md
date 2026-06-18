# Home Graph Reference

Home Graph is owned by the GoodVibes SDK and daemon. The Home Assistant integration gathers Home Assistant context, forwards service and panel calls, and renders daemon responses. It does not store graph data locally, parse uploaded files, synthesize answers, rank snippets, generate pages, or compute map layouts.

Default knowledge space:

```text
homeassistant:<installationId>
```

## Daemon Routes

The integration targets these SDK `0.33.38` Home Graph routes:

- `POST /api/artifacts`
- `POST /api/knowledge/ingest/artifact`
- `GET /api/homeassistant/home-graph/status`
- `POST /api/homeassistant/home-graph/sync`
- `POST /api/homeassistant/home-graph/ingest/url`
- `POST /api/homeassistant/home-graph/ingest/note`
- `POST /api/homeassistant/home-graph/ingest/artifact`
- `POST /api/homeassistant/home-graph/link`
- `POST /api/homeassistant/home-graph/unlink`
- `POST /api/homeassistant/home-graph/ask`
- `POST /api/homeassistant/home-graph/device-passport`
- `POST /api/homeassistant/home-graph/room-page`
- `POST /api/homeassistant/home-graph/packet`
- `GET /api/homeassistant/home-graph/issues`
- `POST /api/homeassistant/home-graph/facts/review`
- `GET /api/homeassistant/home-graph/sources`
- `GET /api/homeassistant/home-graph/pages`
- `GET /api/homeassistant/home-graph/refinement/tasks`
- `GET /api/homeassistant/home-graph/refinement/tasks/{id}`
- `POST /api/homeassistant/home-graph/refinement/run`
- `POST /api/homeassistant/home-graph/refinement/tasks/{id}/cancel`
- `GET /api/homeassistant/home-graph/browse`
- `GET` or `POST /api/homeassistant/home-graph/map`
- `POST /api/homeassistant/home-graph/export`
- `POST /api/homeassistant/home-graph/import`
- `POST /api/homeassistant/home-graph/reset`
- `POST /api/homeassistant/home-graph/reindex`

All Home Graph routes use normal daemon auth. Mutating routes require a daemon token with admin privileges.

## Sidebar Panel

The `GoodVibes Home` sidebar panel talks to Home Assistant, not directly to the daemon:

- Browser UI calls the authenticated Home Assistant websocket command `goodvibes/home_graph/call`.
- Browser file uploads go to `POST /api/goodvibes/home-graph/upload`.
- Home Assistant forwards calls to the daemon with the stored daemon bearer token.

The browser never receives the daemon token.

Panel actions include status/readiness, sync, source/node/edge/issue browsing, visual map, URL/note/reference/file ingest, source-backed questions, link/unlink, review/forget, reindex, SDK refinement task browsing/runs/cancellation, LLM triage of open review issues, generated page inventory, direct page refresh tools, packets, export/import, and reset.

The normal ingest UI only asks for the source. Title, tags, target, relation, and metadata are advanced overrides for corrections, unusual cases, or linking a known manual/source to a specific Home Assistant graph object.

## Workflow

1. Sync Home Assistant context into the daemon.
2. Ingest URLs, notes, documents, photos, manuals, receipts, and troubleshooting details.
3. Let the daemon classify sources, extract facts, link sources to Home Assistant objects, and create review items when confidence is low.
4. Let GoodVibes auto-review high-confidence false positives where available.
5. Review or correct the remaining facts and links in the sidebar.
6. Ask source-backed questions, browse generated pages, inspect the map, or generate packets.

The integration starts a background sync after setup. The sidebar and ingest services sync automatically before ingest. Ask calls also sync automatically if the integration has not sent a snapshot since Home Assistant startup.

The snapshot sent by `goodvibes.sync_home_graph` includes entities, devices, areas, automations, scripts, scenes, labels where available, integrations, helper metadata, selected current state attributes, integration documentation/source candidates, source registry metadata, and bounded page automation for device passports and room pages.

## Ingest

Example sync:

```yaml
action: goodvibes.sync_home_graph
data: {}
```

Example manual URL ingest:

```yaml
action: goodvibes.ingest_url
data:
  url: https://example.com/front-door-lock-manual.pdf
  target_kind: ha_device
  target_id: front-door-lock
  relation: has_manual
```

Example troubleshooting note:

```yaml
action: goodvibes.ingest_note
data:
  note: Last time the front door lock went offline, replacing the CR123A batteries fixed it.
```

Example document or photo ingest by daemon-local path:

```yaml
action: goodvibes.ingest_artifact
data:
  path: /data/manuals/front-door-lock.pdf
```

`goodvibes.ingest_artifact` accepts one of `artifact_id`, `path`, `uri`, or compatibility `url`. The daemon owns artifact storage, processing, extraction, indexing, semantic enrichment, classification, linking, review, and refinement.

Use the sidebar for normal browser file uploads. Do not base64 large PDFs, manuals, receipts, or photos into JSON. The upload bridge accepts multipart browser uploads, writes a temporary file inside Home Assistant, forwards it to the daemon, and removes the temporary file after the daemon call finishes.

Daemon artifact size is controlled by `storage.artifacts.maxBytes`; SDK `0.33.38` defaults to `512 MiB`. Home Assistant and reverse proxies in front of it may need matching upload size and timeout settings for large browser uploads.

URL, note, artifact, import, reindex, and refinement calls allow up to one hour for daemon extraction/indexing. Sync-generated pages, packets, and exports allow up to ten minutes.

## Linking

Use `target_kind`, `target_id`, and optional `relation` when overriding ingest behavior, manually linking/correcting knowledge, or attaching a known object-specific source such as a manual to a device. General notes and sources can omit these fields and let the daemon classify and link automatically.

Common target kinds:

- `ha_entity`: Home Assistant `entity_id`, such as `binary_sensor.front_door`.
- `ha_device`: Home Assistant device registry id.
- `ha_area`: Home Assistant area id.
- `ha_room`: daemon/Home Graph room id when available.
- `ha_automation`: automation entity id or daemon-supported automation id.
- `ha_script`: script entity id.
- `ha_scene`: scene entity id.
- `ha_label`: Home Assistant label id.
- `ha_integration`: Home Assistant integration/config entry id.
- `ha_device_passport`, `ha_maintenance_item`, `ha_troubleshooting_case`, `ha_purchase`, and `ha_network_node`: SDK-owned Home Graph ids.

The older `entity`, `device`, `area`, `automation`, `script`, and `scene` strings remain accepted by the service schema for compatibility.

Common relations:

- `has_manual`
- `has_receipt`
- `has_warranty`
- `uses_battery`
- `has_issue`
- `fixed_by`
- `controls`
- `located_in`
- `connected_via`
- `source_for`

Example link after ingest:

```yaml
action: goodvibes.link_knowledge
data:
  source_id: src_123
  target_kind: ha_entity
  target_id: binary_sensor.front_door
  relation: source_for
```

For missing-manual/source issues, use the Review tab in the sidebar when possible. Selecting an issue exposes upload, URL, and existing-source linking controls that target the selected graph object automatically and then call the daemon review endpoint to resolve the issue.

## Ask

Example graph question:

```yaml
action: goodvibes.ask_home_graph
data:
  query: What battery does the front door lock use?
  include_confidence: true
```

Ask responses are rendered directly from SDK fields. The panel shows the synthesized answer text, confidence/mode, repair/refinement metadata, extracted facts, gaps, linked sources, and linked Home Assistant objects.

Fact cards preserve daemon-provided linkage fields such as `subject`, `subjectIds`, `linkedObjectIds`, and `targetHints` when present. The integration does not infer graph linkage locally.

SDK `0.33.38` also supports `knowledgeSpaceId: "homeassistant"` as a namespace alias for base knowledge Ask calls.

## Pages

Example generated pages request:

```yaml
action: goodvibes.home_graph_pages
data:
  limit: 100
  include_markdown: true
```

The pages response includes `ok`, `spaceId`, and `pages`. Each page has a daemon source record plus optional artifact metadata and markdown content when `include_markdown` is true.

The GoodVibes Home Pages tab renders these records as a wiki-style page browser and reader. Direct regeneration, export/import, and reset controls are kept in collapsed maintenance sections. The reader uses SDK page subject, target, neighbor, and related-page metadata when present, and derives fallback internal navigation from returned page metadata and markdown rows.

Generated pages should be built from canonical typed facts and linked sources returned by the daemon, not duplicate raw evidence lines.

## Map

Example visual map request:

```yaml
action: goodvibes.home_graph_map
data:
  limit: 500
  include_sources: true
  include_generated: true
  domains: media_player,light
  area_ids: living_room,kitchen
```

Map filters are sent to the daemon, not applied locally. Supported generic service fields include `query`, `record_kinds`, `ids`, `linked_to_ids`, `node_kinds`, `source_types`, `source_statuses`, `node_statuses`, `issue_codes`, `issue_statuses`, `issue_severities`, `edge_relations`, `tags`, and `min_confidence`.

Supported Home Assistant fields include `object_kinds`, `entity_ids`, `device_ids`, `area_ids`, `integration_ids`, `integration_domains`, `domains`, `device_classes`, and `labels`.

The sidebar Map tab uses `facets.homeAssistant` counts from the daemon for filter drilldowns. To keep the first view usable, the panel defaults to a smaller graph, leaves sources/pages off until selected, and hides unlabeled raw technical IDs from the primary chip lists while preserving selected exact IDs as removable filters.

## Review

Example review:

```yaml
action: goodvibes.review_fact
data:
  issue_id: issue_123
  action: resolve
```

When the Review tab or panel refresh loads open issues, the bridge asks the daemon conversation endpoint to classify them in small background batches. Only high-confidence `reject` decisions are applied automatically through `/api/homeassistant/home-graph/facts/review`; uncertain cases remain visible for manual review.

Review payloads include semantic facts such as `batteryPowered: false`, `batteryType: "none"`, or `manualRequired: false` when those facts are implied by the selected decision.

The integration persists fingerprints for open issues the LLM has already classified as still requiring manual review, so unchanged issues are not reclassified after a page refresh or Home Assistant restart. Use `Re-run triage` to force a fresh classification.

## Reindex and Refinement

Example reindex after a daemon SDK update:

```yaml
action: goodvibes.home_graph_reindex
data: {}
```

If older manuals were uploaded before searchable extraction or old PDF parsing was available, run `goodvibes.home_graph_reindex` once after updating the daemon to SDK `0.33.38` or newer, then retry Home Graph Ask. No reupload is required. If older manuals were not linked to the right object, re-link them from Review/Link or reingest them.

The reindex response includes `ok`, `spaceId`, `scanned`, `reparsed`, `skipped`, `failed`, `sources`, `failures`, `changedSourceCount`, `forcedSourceCount`, `skippedGeneratedPageArtifactCount`, `refreshedGeneratedPageCount`, `generatedPagePolicyVersion`, optional `coalesced`, optional auto-link results, optional generated page summary, optional `qualityIssues`, and optional semantic counts.

SDK `0.33.38` may also return `semantic.selfImprovement`, refinement task IDs, `truncated`, and `budgetExhausted`. Broad repair work may be queued or coalesced for asynchronous refinement instead of completed inside the reindex request.

The Refine tab lists daemon-owned task records from `/api/homeassistant/home-graph/refinement/tasks`, including lifecycle state, trigger, priority, blocked reason, trace, retry timing such as `nextRepairAttemptAt`, and metadata. It can call `/api/homeassistant/home-graph/refinement/run` for broad or targeted gap/source refinement and `/api/homeassistant/home-graph/refinement/tasks/{id}/cancel` for active task cancellation.

Ask answers may include `answer.refinementTaskIds`; the panel renders those IDs so the matching tasks can be inspected. The latest refinement run summary displays SDK budget fields such as `candidateGaps`, `processedGaps`, `requestedLimit`, `effectiveLimit`, `truncated`, and `budgetExhausted`.

## Export, Import, and Reset

Example reset preview:

```yaml
action: goodvibes.home_graph_reset
data:
  dry_run: true
```

Example destructive reset:

```yaml
action: goodvibes.home_graph_reset
data:
  dry_run: false
  confirm: RESET
```

Do not manually delete SDK database rows or import over the current Home Graph space to recover from bad historical ingest/link/page data. Export/import are for backup and transfer, not reset.

Use the SDK-owned admin reset route for the target `homeassistant:<installationId>` space only. Preview first with `dry_run: true`; destructive reset requires typed `RESET`.

After reset:

1. Sync the Home Assistant snapshot.
2. Reingest or relink manuals and uploads.
3. Run reindex/refinement/page generation.
4. Retest Ask, Pages, and Map from the clean space.

Export first if the current space may be needed for diagnosis.
