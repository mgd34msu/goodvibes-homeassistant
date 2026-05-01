# GoodVibes Home Assistant Integration

Custom Home Assistant integration for the GoodVibes daemon Home Assistant surface from `@pellux/goodvibes-sdk` `0.27.10`.

This integration is the Home Assistant side of the GoodVibes daemon contract. It provides setup, Assist integration, services, sensors, repairs, event handling, a GoodVibes Home sidebar panel, upload proxying, Home Graph snapshot collection, and a daemon-rendered visual knowledge map. The daemon owns GoodVibes routing, model/provider selection, tool catalogs, remote-chat sessions, knowledge storage, graph search, projections, packets, artifacts, automatic Home Graph pages, and wiki rendering.

## Requirements

- GoodVibes daemon using `@pellux/goodvibes-sdk@0.27.10` or newer.
- Home Assistant custom integration installed under `custom_components/goodvibes`.
- A daemon operator bearer token for authenticated daemon APIs.
- A Home Assistant webhook secret configured in the daemon and entered in this integration.
- A Home Assistant long-lived access token configured in the daemon if you want daemon-side Home Assistant state, service, template, and event tools.

## Daemon Configuration

Enable the Home Assistant surface in the GoodVibes daemon:

```json
{
  "featureFlags": {
    "homeassistant-surface": "enabled"
  },
  "surfaces": {
    "homeassistant": {
      "enabled": true,
      "instanceUrl": "http://homeassistant.local:8123",
      "accessToken": "goodvibes://...",
      "webhookSecret": "...",
      "defaultConversationId": "goodvibes",
      "deviceId": "goodvibes-daemon",
      "deviceName": "GoodVibes Daemon",
      "eventType": "goodvibes_message",
      "remoteSessionTtlMs": 1200000
    }
  }
}
```

Important daemon keys:

- `surfaces.homeassistant.instanceUrl`
- `surfaces.homeassistant.accessToken`
- `surfaces.homeassistant.webhookSecret`
- `surfaces.homeassistant.defaultConversationId`
- `surfaces.homeassistant.deviceId`
- `surfaces.homeassistant.deviceName`
- `surfaces.homeassistant.eventType`, default `goodvibes_message`
- `surfaces.homeassistant.remoteSessionTtlMs`, default `1200000`

The Home Assistant long-lived access token belongs in the daemon config as `surfaces.homeassistant.accessToken`. The integration stores the daemon URL, daemon bearer token, webhook secret, event type, and Home Graph settings.

## Installation

Copy `custom_components/goodvibes` into your Home Assistant `custom_components` directory, restart Home Assistant, then add the integration from Settings > Devices & services.

The config flow validates:

- `GET /status`
- `GET /api/homeassistant/health`
- `POST /api/channels/actions/homeassistant/homeassistant-manifest`
- `GET /api/homeassistant/home-graph/status` when Home Graph is enabled

Config fields:

- `Daemon URL`: GoodVibes daemon base URL.
- `Daemon bearer token`: daemon operator token used for normal daemon APIs.
- `Home Assistant webhook secret`: shared secret for `/webhook/homeassistant`.
- `Home Assistant event type`: event bus type to listen for, default `goodvibes_message`.
- `Enable Home Graph`: enables SDK/daemon Home Graph services and sensors.
- `Home Graph installation ID`: stable Home Assistant installation id. Leave blank to derive from `hass.config.uuid`.
- `Home Graph knowledge space ID`: optional explicit daemon knowledge space. Leave blank to use `homeassistant:<installationId>`.

## GoodVibes Home Sidebar

The integration registers an admin-only Home Assistant sidebar panel named `GoodVibes Home`. It follows the same custom-panel and iconset pattern used by HACS: the panel is registered as Home Assistant's `custom` panel with `_panel_custom` config, and the sidebar uses the local `goodvibes:home` iconset from `custom_components/goodvibes/frontend/goodvibes-icons.js`. The source SVG is normalized to a 24x24 `currentColor` path in `custom_components/goodvibes/frontend/gv-icon-sidebar.svg`; the integration brand icon lives at `custom_components/goodvibes/brand/icon.png`.

The panel talks to Home Assistant, not directly to the daemon:

- Browser UI calls the authenticated Home Assistant websocket command `goodvibes/home_graph/call`.
- Browser file uploads go to `POST /api/goodvibes/home-graph/upload`.
- Home Assistant forwards those calls to the daemon with the stored daemon bearer token.

The browser never receives the daemon token.

Panel actions include Home Graph status, sync, source/node/edge/issue browsing, visual map, automatic URL/note/reference/file ingest, source-backed questions, link/unlink, review/forget, reindex, LLM triage of open review issues, automatic page inventory, direct page refresh tools, and packets. The normal ingest UI only asks for the source; title, tags, target, relation, and metadata are advanced overrides for corrections, unusual cases, or linking a known manual/source to a specific Home Assistant graph object. When a missing-manual/source issue is selected in Review, the panel can upload a file, add a URL, or attach an existing source directly to the affected graph object and then resolve the issue through the daemon review API. The Home Assistant bridge automatically syncs current HA entity/device context before ingest so the daemon can classify and link sources against the actual home.

## Assist

After setup, select the GoodVibes conversation entity as the conversation agent in a Home Assistant Assist pipeline.

Assist turns call the synchronous daemon endpoint:

```http
POST /api/homeassistant/conversation
Authorization: Bearer <daemon operator token>
```

The daemon handles each Home Assistant Assist conversation in an isolated remote-chat session and returns `assistant.speechText` or `assistant.text` directly. The integration does not use `/webhook/homeassistant` for Assist responses that need spoken output.

The webhook endpoint remains for automation/service calls that intentionally want queued async behavior:

```http
POST /webhook/homeassistant
```

Cancel active Assist work with `goodvibes.cancel` using a `session_id` or `message_id` when available.

## Home Graph

Home Graph is SDK/daemon-owned. This integration collects Home Assistant context and calls daemon APIs; it does not store, search, or generate graph/wiki data locally. The sidebar Map tab displays the daemon-rendered Home Graph SVG returned by the SDK.

Default knowledge space:

```text
homeassistant:<installationId>
```

The integration supports the SDK `0.27.10` Home Graph daemon routes:

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
- `GET /api/homeassistant/home-graph/browse`
- `GET` or `POST /api/homeassistant/home-graph/map`
- `POST /api/homeassistant/home-graph/export`
- `POST /api/homeassistant/home-graph/import`
- `POST /api/homeassistant/home-graph/reindex`

All Home Graph routes use normal daemon auth. Mutating routes require a daemon token with admin privileges.

The SDK also owns Home Graph wiki rendering, generated page content, and visual map layout. This integration exposes pages/export/import/map as thin daemon calls, but it does not store or render the wiki locally. Generated pages are loaded from `GET /api/homeassistant/home-graph/pages?includeMarkdown=true`. Map requests are sent to the daemon as JSON POST payloads so generic filters and Home Assistant filters stay daemon-owned; the panel only displays the returned SVG and `facets.homeAssistant` filter counts.

Artifact ingest supports:

- JSON control payloads for `artifactId`, `path`, or `uri`.
- `multipart/form-data` uploads with a `file` field.
- Raw binary uploads when the bridge controls the request.

Do not base64 large PDFs, manuals, receipts, or photos into JSON. The sidebar upload bridge accepts multipart from the browser, writes a temporary file inside Home Assistant, and forwards it to the daemon for storage, extraction, classification, linking, and review. Optional metadata fields such as `title`, `tags`, `target`, `allowPrivateHosts`, and `metadata` are only sent when explicitly supplied. Daemon artifact size is controlled by `storage.artifacts.maxBytes`; SDK `0.27.10` defaults to `512 MiB`. Home Assistant and reverse proxies in front of it may need matching upload size and timeout settings for large browser uploads. URL, note, artifact, import, and reindex calls allow up to one hour for daemon extraction/indexing; sync-generated pages, packets, and exports allow up to ten minutes.

## Home Graph Workflow

1. Sync Home Assistant context into the daemon. Sync requests SDK page automation, so device passports and room pages are generated or refreshed by the daemon automatically.
2. Ingest URLs, notes, documents, photos, manuals, receipts, and troubleshooting details.
3. Let the daemon classify, extract facts, link sources to Home Assistant objects, and produce review items when confidence is low.
4. Let GoodVibes auto-review high-confidence false positives, then review or correct only the facts and links that still need human judgment.
5. Ask source-backed Home Graph questions.
6. Surface daemon-reported status, issues, and review items through sensors, repairs, and services.

The snapshot sent by `goodvibes.sync_home_graph` includes entities, devices, areas, automations, scripts, scenes, labels where available, integrations, helper metadata, selected current state attributes, integration documentation/source candidates, source registry metadata, and `pageAutomation` with device passports and room pages enabled. SDK `0.27.10` provides semantic Home Graph answers synthesized by the daemon, returns `answer.text`, `sources`, `linkedObjects`, `facts`, `gaps`, and `synthesized`, keeps `linkedObjects` limited to real Home Assistant graph objects while semantic fact/wiki/gap nodes remain in `facts` or `gaps`, anchors object-specific questions to matching Home Assistant graph nodes, uses strict semantic candidates after object-scoped search so unrelated manuals do not win on generic feature/spec terms, stops generated semantic pages and facts from becoming Home Assistant object anchors, hides stale deterministic facts, filters deterministic facts by query intent, filters optional accessory/setup fragments, USB/HDMI fit notes, handling/safety boilerplate, other weak manual facts, low-value manual boilerplate, truncated deterministic fragments, recommended cable-type snippets, new-features/spec-change boilerplate, remote button-map noise, remote battery-low notes, dry-cloth cleaning notes, and generic service/repair/customer-service boilerplate from feature/spec answers and generated pages, applies the same low-value filter to answer fact prompt lines as source text windows, bounds provider-backed semantic calls with SDK timeout/abort/concurrency controls, prioritizes provider-backed semantic answer synthesis before background enrichment, advertises `semantic-self-improvement`, triggers background semantic self-improvement after sync/ingest/reindex, may include `semantic.selfImprovement` in reindex output, lazily repairs relevant linked manuals before ranking, rejects garbled/raw-PDF extraction text as repair-needed answer material, reparses existing uploaded PDFs without reupload, semantically enriches existing sources, upgrades deterministic enrichment with provider-backed LLM output during ask/reindex when available, repairs weak or binary extracted text, auto-links manuals to Home Assistant nodes by model/entity/device identity, regenerates generated pages with source-backed semantic facts after repair, accepts Home Assistant-style snake_case fields, preserves durable Home Graph review decisions across sync/refresh, returns generated pages through `/api/homeassistant/home-graph/pages`, and returns a visual graph map with SDK-owned filters and Home Assistant facets through `/api/homeassistant/home-graph/map`.

The integration starts a background sync after setup, and the sidebar panel and ingest services call sync automatically before ingest. Ask calls also sync automatically if the integration has not sent a snapshot since Home Assistant startup. When the Review tab or panel refresh loads open issues, the bridge asks the daemon conversation endpoint to classify them in small background batches. Only high-confidence `reject` decisions are applied automatically through `/api/homeassistant/home-graph/facts/review`; uncertain cases remain visible for manual review. Review payloads include semantic facts such as `batteryPowered: false`, `batteryType: "none"`, or `manualRequired: false` when those facts are implied by the selected decision. Missing-manual/source review items expose source-resolution controls in the panel, so a manual PDF, product URL, integration documentation page, or existing daemon source can be linked without manually copying graph IDs. If multiple missing-manual/source issues are selected, the same uploaded file, URL, or existing source can be linked to every selected graph object in one action. The integration persists fingerprints for open issues the LLM has already classified as still requiring manual review, so unchanged issues are not reclassified after a page refresh or Home Assistant restart; use `Re-run triage` to force a fresh classification. The Review queue and unresolved-issues repair only request `status: open` issues, while resolved review records remain daemon-owned history. The panel shows batch progress, auto-reviewed count, remaining open count, and the last batch's decision categories.

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

`ingest_artifact` accepts one of `artifact_id`, `path`, `uri`, or compatibility `url`. The daemon owns artifact storage, processing, extraction, indexing, semantic enrichment, classification, linking, and review. Use the `GoodVibes Home` sidebar panel for normal browser file uploads. For best Home Graph ask results, link object-specific manuals, product pages, photos, notes, and documents to the correct graph object with a relation such as `has_manual`; the Review tab auto-populates the graph target when resolving missing-manual/source issues. If older manuals were uploaded before searchable extraction or old PDF parsing was available, run `goodvibes.home_graph_reindex` once after updating the daemon to SDK `0.27.10` or newer, then retry Ask The House. No reupload is required. SDK `0.27.10` can repair weak PDF extraction, semantically enrich existing sources, upgrade deterministic enrichment with provider-backed LLM output, auto-link manuals to matching Home Assistant nodes, regenerate source-backed pages during reindex, filter weak and boilerplate manual facts from generated content and answer fact prompt lines, prioritize provider-backed answer synthesis before background enrichment, trigger background semantic self-improvement, and keep broad reindex semantic work inside the SDK's bounded LLM budget. The GoodVibes Home panel exposes this as `Reindex uploads` in the top bar and Ask tab. If older manuals were not linked to the right object, re-link them from Review/Link or reingest them.

Example reindex after a daemon SDK update:

```yaml
action: goodvibes.home_graph_reindex
data: {}
```

The reindex response includes `ok`, `spaceId`, `scanned`, `reparsed`, `skipped`, `failed`, `sources`, `failures`, optional auto-link results, optional generated page summary, and optional semantic counts under `semantic.scanned`, `semantic.enriched`, `semantic.skipped`, `semantic.failed`, and `semantic.errors`. SDK `0.27.10` may also return `semantic.selfImprovement`.

Example generated pages request:

```yaml
action: goodvibes.home_graph_pages
data:
  limit: 100
  include_markdown: true
```

The pages response includes `ok`, `spaceId`, and `pages`. Each page has a daemon source record plus optional artifact metadata and markdown content when `include_markdown` is true.

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

Map filters are sent to the daemon, not applied locally. Supported generic service fields include `query`, `record_kinds`, `ids`, `linked_to_ids`, `node_kinds`, `source_types`, `source_statuses`, `node_statuses`, `issue_codes`, `issue_statuses`, `issue_severities`, `edge_relations`, `tags`, and `min_confidence`. Supported Home Assistant fields include `object_kinds`, `entity_ids`, `device_ids`, `area_ids`, `integration_ids`, `integration_domains`, `domains`, `device_classes`, and `labels`. The sidebar Map tab uses `facets.homeAssistant` counts from the daemon for its filter chips.

Example graph question:

```yaml
action: goodvibes.ask_home_graph
data:
  query: What battery does the front door lock use?
  include_confidence: true
```

Ask responses are rendered directly from SDK fields. The panel shows the synthesized answer text, confidence/mode, extracted facts, gaps, linked sources, and linked Home Assistant objects. The integration does not parse PDFs, rank snippets, or synthesize answers locally.

Example room page request:

```yaml
action: goodvibes.room_page
data:
  area_id: kitchen
```

Example packet request:

```yaml
action: goodvibes.home_graph_packet
data:
  packet_type: pet_sitter
```

## Home Graph Linking

Use `target_kind`, `target_id`, and optional `relation` when overriding ingest behavior, manually linking/correcting knowledge, or attaching a known object-specific source such as a manual to a device. General notes and sources can omit these fields and let the daemon classify and link automatically.

Common target kinds:

- `ha_entity`: use a Home Assistant `entity_id`, such as `binary_sensor.front_door`.
- `ha_device`: use a Home Assistant device registry id.
- `ha_area`: use a Home Assistant area id.
- `ha_room`: use a daemon/Home Graph room id when available.
- `ha_automation`: use an automation entity id or daemon-supported automation id.
- `ha_script`: use a script entity id.
- `ha_scene`: use a scene entity id.
- `ha_label`: use a Home Assistant label id.
- `ha_integration`: use a Home Assistant integration/config entry id.
- `ha_device_passport`, `ha_maintenance_item`, `ha_troubleshooting_case`, `ha_purchase`, and `ha_network_node`: use SDK-owned Home Graph ids.

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

Example link after ingest:

```yaml
action: goodvibes.link_knowledge
data:
  source_id: src_123
  target_kind: ha_entity
  target_id: binary_sensor.front_door
  relation: source_for
```

Example review:

```yaml
action: goodvibes.review_fact
data:
  issue_id: issue_123
  action: resolve
```

For missing-manual/source issues, use the Review tab in the sidebar when possible. Selecting one issue exposes upload, URL, and existing-source linking controls that target the selected graph object automatically and then call the daemon review endpoint to resolve the issue.

Example issue/source inspection:

```yaml
action: goodvibes.home_graph_issues
data: {}
```

```yaml
action: goodvibes.home_graph_sources
data: {}
```

## Services

Conversation and daemon services:

- `goodvibes.prompt`: async webhook prompt for automations.
- `goodvibes.run_agent`: compatibility task-style async webhook prompt.
- `goodvibes.status`: daemon, runtime task, run, or local remote-chat status.
- `goodvibes.cancel`: cancel active remote-chat work, runtime tasks, or runs.
- `goodvibes.call_tool`: invoke a daemon-exposed Home Assistant tool.

Home Graph services:

- `goodvibes.home_graph_status`
- `goodvibes.sync_home_graph`
- `goodvibes.ingest_url`
- `goodvibes.ingest_note`
- `goodvibes.ingest_artifact`
- `goodvibes.link_knowledge`
- `goodvibes.unlink_knowledge`
- `goodvibes.ask_home_graph`
- `goodvibes.device_passport`
- `goodvibes.room_page`
- `goodvibes.home_graph_packet`
- `goodvibes.home_graph_issues`
- `goodvibes.review_fact`
- `goodvibes.home_graph_sources`
- `goodvibes.home_graph_pages`
- `goodvibes.home_graph_browse`
- `goodvibes.home_graph_map`
- `goodvibes.home_graph_export`
- `goodvibes.home_graph_import`
- `goodvibes.home_graph_reindex`

Example async prompt:

```yaml
action: goodvibes.prompt
data:
  message: turn on the kitchen lights
  conversation_id: home
  area_id: kitchen
  tools:
    - homeassistant_state
    - homeassistant_call_service
```

Example daemon-exposed tool call:

```yaml
action: goodvibes.call_tool
data:
  tool: homeassistant_state
  input:
    entityId: light.kitchen
```

Example cancellation:

```yaml
action: goodvibes.cancel
data:
  session_id: ha-chat-sess-1234
```

## Sensors

Diagnostic sensors:

- Daemon status
- Last reply
- Active session ID
- Active message ID
- Active agent ID
- Last error
- Tool catalog status
- Home Graph status
- Home Graph issues
- Home Graph sources

Home Graph sensor attributes include installation id, knowledge space id, last sync time, daemon status payload, issue payload, source payload, and last Home Graph error.

## Repairs

The integration creates Home Assistant repairs for:

- Home Graph endpoint unavailable.
- Daemon-reported unresolved Home Graph issues.

Use `goodvibes.home_graph_issues` or the Home Graph issues sensor for details.

## Event Handling

GoodVibes publishes back into Home Assistant through the Home Assistant REST event bus:

```http
POST /api/events/goodvibes_message
Authorization: Bearer <Home Assistant long-lived access token>
```

The integration listens for `goodvibes_message` by default. If you configure a custom daemon event type, use the same value in the integration config flow.

## Boundaries

This integration intentionally stays thin:

- It does not implement GoodVibes model/provider routing.
- It does not implement local Home Graph storage.
- It does not render the daemon knowledge wiki or compute local graph layouts.
- It does not duplicate daemon packets, projections, source inventory, graph browsing, or search.
- It does not manage Home Assistant long-lived access tokens for the daemon.

The daemon is the source of truth. Home Assistant supplies context, service calls, sensors, repairs, Assist plumbing, and event handling.
