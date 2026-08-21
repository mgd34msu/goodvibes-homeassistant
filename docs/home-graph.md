# Home Graph reference

Home Graph is owned by the GoodVibes SDK and daemon. The Home Assistant integration gathers Home Assistant context, forwards service and panel calls, and renders daemon responses. It does not store graph data locally, parse uploaded files, synthesize answers, rank snippets, generate pages, or compute map layouts.

Default knowledge space:

```text
homeassistant:<installationId>
```

## Daemon routes

The integration targets these daemon Home Graph routes (latest SDK, validated against `1.3.0`),
one per `client.py` method:

| Route | What it does |
| --- | --- |
| `GET /api/homeassistant/home-graph/status` | Return daemon Home Graph status. |
| `POST /api/homeassistant/home-graph/sync` | Submit a Home Graph snapshot sync. |
| `POST /api/homeassistant/home-graph/ingest/url` | Ingest a URL into Home Graph. |
| `POST /api/homeassistant/home-graph/ingest/note` | Ingest a note into Home Graph. |
| `POST /api/homeassistant/home-graph/ingest/artifact` | Ingest an artifact, document, or photo (also the target for multipart browser uploads). |
| `POST /api/homeassistant/home-graph/link` | Link a Home Graph source or node to a Home Assistant object. |
| `POST /api/homeassistant/home-graph/unlink` | Unlink a Home Graph source or node from a Home Assistant object. |
| `POST /api/homeassistant/home-graph/ask` | Ask a source-backed Home Graph question. |
| `POST /api/homeassistant/home-graph/device-passport` | Refresh or retrieve a Home Graph device passport. |
| `POST /api/homeassistant/home-graph/room-page` | Generate or refresh a Home Graph room page. |
| `POST /api/homeassistant/home-graph/packet` | Generate a scoped Home Graph packet. |
| `GET /api/homeassistant/home-graph/issues` | List Home Graph issues. |
| `POST /api/homeassistant/home-graph/facts/review` | Review a Home Graph fact. |
| `GET /api/homeassistant/home-graph/sources` | List Home Graph sources. |
| `GET /api/homeassistant/home-graph/pages` | List daemon-rendered Home Graph generated pages. |
| `GET /api/homeassistant/home-graph/refinement/tasks` | List Home Graph refinement tasks. |
| `GET /api/homeassistant/home-graph/refinement/tasks/{id}` | Return one Home Graph refinement task. |
| `POST /api/homeassistant/home-graph/refinement/run` | Run Home Graph refinement. |
| `POST /api/homeassistant/home-graph/refinement/tasks/{id}/cancel` | Cancel a queued or active Home Graph refinement task. |
| `GET /api/homeassistant/home-graph/browse` | Browse Home Graph nodes and links. |
| `GET` or `POST /api/homeassistant/home-graph/map` | Return the daemon-rendered Home Graph visual map. |
| `POST /api/homeassistant/home-graph/export` | Request a daemon-owned Home Graph export. |
| `POST /api/homeassistant/home-graph/import` | Request a daemon-owned Home Graph import. |
| `POST /api/homeassistant/home-graph/reset` | Request a daemon-owned Home Graph space reset. |
| `POST /api/homeassistant/home-graph/reindex` | Repair missing or weak Home Graph source extraction. |

All Home Graph routes use normal daemon auth. Mutating routes require a daemon token with admin privileges.

An earlier version of this table also listed `POST /api/artifacts` and `POST /api/knowledge/ingest/artifact`. Checked against the `goodvibes-sdk` checkout: both are real daemon routes (`artifacts.create` and `knowledge.ingest.artifact` in the operator contract), but neither is Home Graph-scoped or Home-Assistant-scoped. `POST /api/artifacts` is the daemon's generic artifact-storage primitive (`packages/sdk/src/platform/control-plane/method-catalog-media.ts`); `POST /api/knowledge/ingest/artifact` ingests into the daemon's generic structured knowledge store (`packages/sdk/src/platform/control-plane/method-catalog-knowledge.ts`), a different store from Home Graph. The daemon's own `/api/homeassistant/home-graph/ingest/artifact` handler (`packages/sdk/src/platform/daemon/http/home-graph-routes.ts`) reuses the same underlying artifact-store primitive internally for uploads, then calls `homeGraphService.ingestArtifact`, not `knowledge.ingest.artifact`. So the two dropped routes were never this integration's path; they belong to an unrelated daemon subsystem, and the table above is the complete and accurate route list this integration actually calls.

## Sidebar panel

The `GoodVibes Home` sidebar panel talks to Home Assistant, not directly to the daemon:

- Browser UI calls the authenticated Home Assistant websocket command `goodvibes/home_graph/call`.
- Browser file uploads go to `POST /api/goodvibes/home-graph/upload`.
- Home Assistant forwards calls to the daemon with the stored daemon bearer token.

The browser never receives the daemon token.

Every action the panel can send over `goodvibes/home_graph/call` dispatches to one handler in
`frontend.py`'s `ACTION_HANDLERS` table:

| Action | What it does |
| --- | --- |
| `status` | Refresh and return Home Graph readiness/status. |
| `sync` | Send the Home Assistant context snapshot to the daemon (see Workflow below). |
| `sources` | List Home Graph sources. |
| `pages` | List generated pages, optionally with markdown. |
| `issues` | List Home Graph issues (defaults to `status: open`). |
| `browse` | Browse nodes and links. |
| `map` | Return the daemon-rendered visual map for the given filters. |
| `export` | Export the daemon-owned knowledge space. |
| `import` | Import a previously exported knowledge space. |
| `reset` | Preview or perform a destructive reset (typed `RESET` required unless `dry_run`). |
| `reindex` | Reindex and semantically enrich existing uploads without reuploading files. |
| `refinement_tasks` | List refinement task records. |
| `refinement_task` | Return one refinement task by ID. |
| `refinement_run` | Run refinement, broad or targeted by gap/source IDs. |
| `refinement_cancel` | Cancel a queued or active refinement task. |
| `ask` | Ask a source-backed question; syncs first if nothing has synced yet this session. |
| `ingest_url` | Ingest a URL. |
| `ingest_note` | Ingest a note; syncs context first. |
| `ingest_artifact` | Ingest an existing artifact, daemon-local path, or URI. |
| `link` | Link a source or node to a Home Assistant object. |
| `unlink` | Remove a link between a source/node and a Home Assistant object. |
| `review` | Review, resolve, edit, reject, accept, or forget an issue, source, or node. |
| `triage_issues` | Run the daemon's LLM triage over open review issues in the background. |
| `device_passport` | Refresh or retrieve a device passport. |
| `room_page` | Generate or refresh a room page. |
| `packet` | Generate a scoped packet (see [services.md](services.md#ask-pages-and-packets) for the packet types). |

The normal ingest UI only asks for the source. Title, tags, target, relation, and metadata are advanced overrides for corrections, unusual cases, or linking a known manual/source to a specific Home Assistant graph object.

## Workflow

1. Sync Home Assistant context into the daemon.
2. Ingest URLs, notes, documents, photos, manuals, receipts, and troubleshooting details.
3. Let the daemon classify sources, extract facts, link sources to Home Assistant objects, and create review items when confidence is low.
4. Let GoodVibes auto-review high-confidence false positives where available.
5. Review or correct the remaining facts and links in the sidebar.
6. Ask source-backed questions, browse generated pages, inspect the map, or generate packets.

The integration starts a background sync after setup. The sidebar and ingest services sync automatically before ingest. Ask calls also sync automatically if the integration has not sent a snapshot since Home Assistant startup.

`async_build_home_graph_snapshot` (`home_graph.py`) assembles what `goodvibes.sync_home_graph`
sends:

| Snapshot content | What it carries |
| --- | --- |
| Entities | Registry entities exposed to assistants (or all of them, with "include entities not exposed to assistants"), each with its state, a filtered set of current attributes, and registry metadata. |
| Devices | Devices that own at least one included entity. |
| Areas | Areas resolved from included entities or their devices. |
| Automations, scripts, scenes | The subset of the entities above in those three domains. |
| Labels | Home Assistant labels, when the label registry has any. |
| Integrations | One record per configured integration domain: entry count and state, plus documentation, source, and issue-tracker URLs when the integration's manifest/repo metadata supplies them. |
| Helper metadata | Entities in a fixed set of helper domains (`input_boolean`, `input_number`, `counter`, and the rest of `HELPER_DOMAINS`), singled out under `metadata.helpers`. |
| Bounded page automation | Default hints for generating device passports and room pages (`pageAutomation`). |

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

Daemon artifact size is controlled by `storage.artifacts.maxBytes`; the latest SDK defaults to `512 MiB`. Home Assistant and reverse proxies in front of it may need matching upload size and timeout settings for large browser uploads.

URL, note, artifact, import, reindex, and refinement calls allow up to one hour for daemon extraction/indexing. Sync-generated pages, packets, and exports allow up to ten minutes.

## Linking

Use `target_kind`, `target_id`, and optional `relation` when overriding ingest behavior, manually linking/correcting knowledge, or attaching a known object-specific source such as a manual to a device. General notes and sources can omit these fields and let the daemon classify and link automatically.

`target_kind` names which kind of graph object the link points at, and
`target_id` carries that object's id. Most links target the synced registry
kinds; the last five rows are objects the daemon itself records or that you
record deliberately. This table is the authoritative reference in this repo;
`services.md` links here instead of repeating it.

| Target kind | What it represents | Which id to pass |
| --- | --- | --- |
| `ha_entity` | One synced entity | The Home Assistant `entity_id`, such as `binary_sensor.front_door` |
| `ha_device` | A synced device | The device registry id |
| `ha_area` | A synced area | The area id |
| `ha_room` | A room recorded in the graph itself, distinct from an area | The daemon's room id when one exists |
| `ha_automation` | A synced automation | The automation entity id |
| `ha_script` | A synced script | The script entity id |
| `ha_scene` | A synced scene | The scene entity id |
| `ha_label` | A synced label | The label id |
| `ha_integration` | An installed integration | The integration/config entry id |
| `ha_device_passport` | The generated living device profile for one device | The daemon-owned Home Graph id |
| `ha_maintenance_item` | A maintenance task or schedule entry you record | The daemon-owned Home Graph id |
| `ha_troubleshooting_case` | A recorded troubleshooting episode | The daemon-owned Home Graph id |
| `ha_purchase` | A purchase record for something in the home | The daemon-owned Home Graph id |
| `ha_network_node` | A router, switch, access point, or other network element you record | The daemon-owned Home Graph id |

The service selector also offers generic `source` and `node` kinds for linking
by raw daemon record id, and the older `entity`, `device`, `area`,
`automation`, `script`, and `scene` strings remain accepted for compatibility.

`relation` says what the link means. Omitting it is always safe: the daemon
classifies manuals, receipts, and warranties on its own during ingest, and
plain links default to `source_for`. Supply a relation when you want to state
the meaning explicitly.

| Relation | What it means | When to supply it |
| --- | --- | --- |
| `source_for` | The general "this backs that" link from a source to an object | Rarely needed; it is the default when `relation` is omitted |
| `has_manual` | The source is the object's manual | Only to override the daemon's own manual classification |
| `has_receipt` | The source is a purchase receipt | Only to override the automatic receipt classification |
| `has_warranty` | The source is warranty documentation | Only to override the automatic warranty classification |
| `located_in` | The object sits in an area or room | The daemon writes this during sync; supply it for manual placement corrections |
| `belongs_to_device` | An entity or object belongs to a device | The daemon writes this during sync; supply it for manual corrections |
| `connected_via` | The object reaches Home Assistant through an integration | The daemon writes this during sync; supply it for manual corrections |
| `has_issue` | The object has a recorded problem | When linking a note or source that documents a problem |
| `fixed_by` | A problem was resolved by this source | When recording what fixed an issue |
| `controls` | One object drives another, such as an automation controlling a light | When recording control relationships the registries do not express |
| `uses_battery` | The device runs on a battery worth tracking | When recording battery dependencies |
| `part_of_network` | The object is part of the home network | When building out network topology around `ha_network_node` objects |
| `mentioned_by` | A source mentions the object without being about it | When a document references an object in passing |

One further relation, `repairs_gap`, appears on edges the daemon writes itself
when an ingested source repairs a recorded knowledge gap. It is not a value to
supply on a link call.

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

The latest SDK also supports `knowledgeSpaceId: "homeassistant"` as a namespace alias for base knowledge Ask calls.

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

Map filters are sent to the daemon, not applied locally. Field descriptions below are from
`services.yaml`, the same source `services.md`'s copy of these tables draws from.

| Generic field | What it filters |
| --- | --- |
| `query` | Free-text search across matched records. |
| `record_kinds` | Comma-separated record kinds such as `source`, `node`, `issue`. |
| `ids` | Comma-separated source, node, or issue IDs. |
| `linked_to_ids` | Comma-separated record IDs to show directly linked records. |
| `node_kinds` | Comma-separated node kinds. |
| `source_types` | Comma-separated source types. |
| `source_statuses` | Comma-separated source statuses. |
| `node_statuses` | Comma-separated node statuses. |
| `issue_codes` | Comma-separated issue codes. |
| `issue_statuses` | Comma-separated issue statuses. |
| `issue_severities` | Comma-separated issue severities. |
| `edge_relations` | Comma-separated edge relations. |
| `tags` | Comma-separated tags or labels. |
| `min_confidence` | Minimum confidence, `0`-`1`. |

| Home Assistant field | What it filters |
| --- | --- |
| `object_kinds` | Comma-separated Home Assistant object kinds. |
| `entity_ids` | Comma-separated Home Assistant entity IDs. |
| `device_ids` | Comma-separated Home Assistant device IDs. |
| `area_ids` | Comma-separated Home Assistant area IDs. |
| `integration_ids` | Comma-separated Home Assistant integration IDs. |
| `integration_domains` | Comma-separated Home Assistant integration domains. |
| `domains` | Comma-separated Home Assistant entity domains. |
| `device_classes` | Comma-separated Home Assistant device classes. |
| `labels` | Comma-separated Home Assistant labels. |

The sidebar Map tab uses `facets.homeAssistant` counts from the daemon for filter drilldowns. To keep the first view usable, the panel defaults to a smaller graph, leaves sources/pages off until selected, and hides unlabeled raw technical IDs from the primary chip lists while preserving selected exact IDs as removable filters.

## Review

Example review:

```yaml
action: goodvibes.review_fact
data:
  issue_id: issue_123
  action: resolve
```

When the Review tab or panel refresh loads open issues, it calls `/api/homeassistant/home-graph/refinement/run` with a `triage` body in small background batches; the daemon's own LLM triage loop classifies each issue and, above its confidence threshold, applies `reject` decisions automatically through `facts/review`. Uncertain cases remain visible for manual review.

Review payloads include semantic facts such as `batteryPowered: false`, `batteryType: "none"`, or `manualRequired: false` when those facts are implied by the selected decision, derived daemon-side, not by the integration.

The daemon persists a per-issue decision cache so unchanged open issues are not reclassified after a page refresh or Home Assistant restart. Use `Re-run triage` to force a fresh classification. A daemon with no configured triage LLM, or one that predates server-side triage, reports that honestly instead of running a local fallback engine.

## Reindex and refinement

Example reindex after a daemon SDK update:

```yaml
action: goodvibes.home_graph_reindex
data: {}
```

If older manuals were uploaded before searchable extraction or old PDF parsing was available, run `goodvibes.home_graph_reindex` once after updating the daemon to the latest SDK, then retry Home Graph Ask. No reupload is required. If older manuals were not linked to the right object, re-link them from Review/Link or reingest them.

The reindex response is a daemon-owned payload this integration forwards to the panel as-is,
with no local per-field parsing to verify field meaning against; `client.py`'s
`home_graph_reindex` returns the daemon's JSON body unchanged. As of the SDK version this
integration is validated against, that body carries `ok`, `spaceId`, `scanned`, `reparsed`,
`skipped`, `failed`, `sources`, `failures`, `changedSourceCount`, `forcedSourceCount`,
`skippedGeneratedPageArtifactCount`, `refreshedGeneratedPageCount`, `generatedPagePolicyVersion`,
optional `coalesced`, optional auto-link results, optional generated page summary, optional
`qualityIssues`, and optional semantic counts.

The latest SDK may also return `semantic.selfImprovement`, refinement task IDs, `truncated`, and
`budgetExhausted`. Broad repair work may be queued or coalesced for asynchronous refinement
instead of completed inside the reindex request.

The Refine tab lists daemon-owned task records from `/api/homeassistant/home-graph/refinement/tasks`, including lifecycle state, trigger, priority, blocked reason, trace, retry timing such as `nextRepairAttemptAt`, and metadata. It can call `/api/homeassistant/home-graph/refinement/run` for broad or targeted gap/source refinement and `/api/homeassistant/home-graph/refinement/tasks/{id}/cancel` for active task cancellation.

Ask answers may include `answer.refinementTaskIds`; the panel renders those IDs so the matching tasks can be inspected. The refinement run response is likewise forwarded unparsed (`client.py`'s `home_graph_refinement_run`), so these budget field names come from the daemon's own summary rather than local field-by-field handling: `candidateGaps`, `processedGaps`, `requestedLimit`, `effectiveLimit`, `truncated`, and `budgetExhausted`.

## Export, import, and reset

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
