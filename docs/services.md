# Service Reference

Home Assistant service selectors and full field metadata live in [custom_components/goodvibes/services.yaml](../custom_components/goodvibes/services.yaml). This page explains how the services are grouped and how to use the common fields.

Most services accept `config_entry_id`. Omit it when there is only one GoodVibes config entry. Include it when multiple daemon entries are installed.

## Conversation and Daemon Services

| Service | Purpose |
| --- | --- |
| `goodvibes.prompt` | Submit an async prompt through the GoodVibes Home Assistant webhook. |
| `goodvibes.run_agent` | Compatibility task-style async webhook prompt. |
| `goodvibes.status` | Inspect daemon, Home Assistant surface, runtime task, run, or local remote-chat status. |
| `goodvibes.cancel` | Cancel active remote-chat work, runtime tasks, or runs. |
| `goodvibes.call_tool` | Invoke a daemon-exposed Home Assistant tool. |

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

Example task-style prompt:

```yaml
action: goodvibes.run_agent
data:
  task: Summarize which lights are currently on.
  conversation_id: home
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

## Home Graph Services

| Service | Purpose |
| --- | --- |
| `goodvibes.home_graph_status` | Inspect daemon Home Graph status for this Home Assistant installation. |
| `goodvibes.sync_home_graph` | Send registry, entity, state, helper, integration, and source context to the daemon. |
| `goodvibes.ingest_url` | Ingest a URL into Home Graph. |
| `goodvibes.ingest_note` | Ingest a note into Home Graph. |
| `goodvibes.ingest_artifact` | Ingest an existing GoodVibes artifact, daemon-local file path, URI, or compatibility URL. |
| `goodvibes.link_knowledge` | Link a Home Graph source or node to a Home Assistant object. |
| `goodvibes.unlink_knowledge` | Remove a link between a Home Graph source/node and a Home Assistant object. |
| `goodvibes.ask_home_graph` | Ask a source-backed question against Home Graph. |
| `goodvibes.device_passport` | Refresh or retrieve a device passport. |
| `goodvibes.room_page` | Request generation of a room page. |
| `goodvibes.home_graph_packet` | Request a scoped packet such as a guest guide or emergency sheet. |
| `goodvibes.home_graph_issues` | List Home Graph issues. |
| `goodvibes.review_fact` | Review, resolve, edit, reject, accept, or forget a Home Graph issue, source, or node. |
| `goodvibes.home_graph_sources` | List Home Graph sources. |
| `goodvibes.home_graph_pages` | List generated pages. |
| `goodvibes.home_graph_browse` | Browse nodes and links. |
| `goodvibes.home_graph_map` | Return the daemon-rendered visual map. |
| `goodvibes.home_graph_export` | Export the daemon-owned knowledge space. |
| `goodvibes.home_graph_import` | Import a daemon-owned knowledge space export. |
| `goodvibes.home_graph_reset` | Preview or reset one daemon-owned knowledge space. |
| `goodvibes.home_graph_reindex` | Reindex and semantically enrich existing Home Graph uploads without reuploading files. |

## Ingest Examples

Sync current Home Assistant context:

```yaml
action: goodvibes.sync_home_graph
data: {}
```

Ingest a manual URL and link it to a device:

```yaml
action: goodvibes.ingest_url
data:
  url: https://example.com/front-door-lock-manual.pdf
  target_kind: ha_device
  target_id: front-door-lock
  relation: has_manual
```

Ingest a troubleshooting note:

```yaml
action: goodvibes.ingest_note
data:
  title: Front door lock offline fix
  note: Replacing the CR123A batteries fixed the front door lock after it went offline.
  target_kind: ha_entity
  target_id: lock.front_door
  relation: fixed_by
```

Ingest an existing daemon-local file:

```yaml
action: goodvibes.ingest_artifact
data:
  path: /data/manuals/front-door-lock.pdf
```

For browser file uploads, use the `GoodVibes Home` sidebar panel. Browser uploads are multipart requests to Home Assistant, then Home Assistant forwards them to the daemon.

## Linking Fields

Use `target_kind`, `target_id`, and optional `relation` when the daemon needs a hint or when manually correcting a link.

Common `target_kind` values:

- `ha_entity`
- `ha_device`
- `ha_area`
- `ha_room`
- `ha_automation`
- `ha_script`
- `ha_scene`
- `ha_label`
- `ha_integration`
- `ha_device_passport`
- `ha_maintenance_item`
- `ha_troubleshooting_case`
- `ha_purchase`
- `ha_network_node`

Compatibility values accepted by the service schema:

- `entity`
- `device`
- `area`
- `automation`
- `script`
- `scene`

Common `relation` values:

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

Manual link example:

```yaml
action: goodvibes.link_knowledge
data:
  source_id: src_123
  target_kind: ha_entity
  target_id: binary_sensor.front_door
  relation: source_for
```

Manual unlink example:

```yaml
action: goodvibes.unlink_knowledge
data:
  source_id: src_123
  target_kind: ha_entity
  target_id: binary_sensor.front_door
  relation: source_for
```

## Ask, Pages, and Packets

Ask a source-backed question:

```yaml
action: goodvibes.ask_home_graph
data:
  query: What battery does the front door lock use?
  include_sources: true
  include_linked_objects: true
  include_confidence: true
```

Request generated pages:

```yaml
action: goodvibes.home_graph_pages
data:
  limit: 100
  include_markdown: true
```

Request a room page:

```yaml
action: goodvibes.room_page
data:
  area_id: kitchen
```

Request a packet:

```yaml
action: goodvibes.home_graph_packet
data:
  packet_type: pet_sitter
```

Supported packet types:

- `guest_guide`
- `pet_sitter`
- `hvac_notes`
- `electrician_notes`
- `network_closet`
- `emergency_sheet`
- `house_sitter`

## Review

List open issues:

```yaml
action: goodvibes.home_graph_issues
data:
  status: open
```

Resolve an issue:

```yaml
action: goodvibes.review_fact
data:
  issue_id: issue_123
  action: resolve
```

Accepted review actions:

- `accept`
- `reject`
- `resolve`
- `edit`
- `forget`

`fact_id` is accepted as a compatibility alias for `issue_id`. `decision` is accepted as a compatibility alias for `action`.

## Map Filters

Example visual map request:

```yaml
action: goodvibes.home_graph_map
data:
  limit: 500
  include_sources: true
  include_issues: false
  include_generated: true
  domains: media_player,light
  area_ids: living_room,kitchen
```

Generic filter fields:

- `query`
- `record_kinds`
- `ids`
- `linked_to_ids`
- `node_kinds`
- `source_types`
- `source_statuses`
- `node_statuses`
- `issue_codes`
- `issue_statuses`
- `issue_severities`
- `edge_relations`
- `tags`
- `min_confidence`

Home Assistant filter fields:

- `object_kinds`
- `entity_ids`
- `device_ids`
- `area_ids`
- `integration_ids`
- `integration_domains`
- `domains`
- `device_classes`
- `labels`

Comma-separated string fields are passed to the daemon as filters. The integration does not compute the graph layout or apply map filters locally.

## Reindex, Export, Import, and Reset

Reindex existing uploads after a daemon SDK update:

```yaml
action: goodvibes.home_graph_reindex
data: {}
```

Export the selected knowledge space:

```yaml
action: goodvibes.home_graph_export
data: {}
```

Reset preview:

```yaml
action: goodvibes.home_graph_reset
data:
  dry_run: true
```

Destructive reset:

```yaml
action: goodvibes.home_graph_reset
data:
  dry_run: false
  confirm: RESET
```

Use export/import for backup and transfer. Use reset for recovering from bad historical ingest, bad links, or contaminated generated page data. Do not import over the current space as a reset substitute.
