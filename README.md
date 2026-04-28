# GoodVibes Home Assistant Integration

Custom Home Assistant integration for the GoodVibes daemon Home Assistant surface from `@pellux/goodvibes-sdk` `0.26.0`.

This integration is the Home Assistant side of the GoodVibes daemon contract. It provides setup, Assist integration, services, sensors, repairs, event handling, and Home Graph snapshot collection. The daemon owns GoodVibes routing, model/provider selection, tool catalogs, remote-chat sessions, knowledge storage, graph search, projections, packets, and wiki rendering.

## Requirements

- GoodVibes daemon using `@pellux/goodvibes-sdk@0.26.0` or newer.
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

Home Graph is SDK/daemon-owned. This integration collects Home Assistant context and calls daemon APIs; it does not store, search, or render graph/wiki data locally.

Default knowledge space:

```text
homeassistant:<installationId>
```

The integration supports the SDK `0.26.0` Home Graph daemon routes:

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
- `GET /api/homeassistant/home-graph/browse`

All Home Graph routes use normal daemon auth. Mutating routes require a daemon token with admin privileges.

The SDK also owns Home Graph export/import and wiki rendering. Those are daemon/web UI concerns, not local Home Assistant storage.

## Home Graph Workflow

1. Sync Home Assistant context into the daemon.
2. Ingest URLs, notes, documents, photos, manuals, receipts, and troubleshooting details.
3. Link sources or graph nodes to Home Assistant objects.
4. Ask source-backed Home Graph questions.
5. Surface daemon-reported status, issues, and review items through sensors, repairs, and services.

The snapshot sent by `goodvibes.sync_home_graph` includes entities, devices, areas, automations, scripts, scenes, labels where available, integrations, helper metadata, and selected current state attributes.

Example sync:

```yaml
action: goodvibes.sync_home_graph
data: {}
```

Example manual URL ingest linked to a device:

```yaml
action: goodvibes.ingest_url
data:
  url: https://example.com/front-door-lock-manual.pdf
  title: Front door lock manual
  target_kind: device
  target_id: front-door-lock
  relation: has_manual
```

Example troubleshooting note:

```yaml
action: goodvibes.ingest_note
data:
  title: Front door lock offline fix
  note: Last time the front door lock went offline, replacing the CR123A batteries fixed it.
  target_kind: device
  target_id: front-door-lock
  relation: has_issue
```

Example document or photo ingest:

```yaml
action: goodvibes.ingest_artifact
data:
  path: /config/www/manuals/front-door-lock.pdf
  title: Front door lock manual
  content_type: application/pdf
  target_kind: device
  target_id: front-door-lock
  relation: has_manual
```

`ingest_artifact` accepts one of `artifact_id`, `media_id`, `path`, or `url`. The daemon owns artifact processing and extraction.

Example graph question:

```yaml
action: goodvibes.ask_home_graph
data:
  query: What battery does the front door lock use?
```

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

Use `target_kind`, `target_id`, and optional `relation` when ingesting or linking knowledge.

Common target kinds:

- `entity`: use a Home Assistant `entity_id`, such as `binary_sensor.front_door`.
- `device`: use a Home Assistant device registry id.
- `area`: use a Home Assistant area id.
- `automation`: use an automation entity id or daemon-supported automation id.
- `script`: use a script entity id.
- `scene`: use a scene entity id.

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
  target_kind: entity
  target_id: binary_sensor.front_door
  relation: source_for
```

Example review:

```yaml
action: goodvibes.review_fact
data:
  fact_id: fact_123
  decision: accept
```

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
- `goodvibes.home_graph_browse`

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
- It does not render the daemon knowledge wiki.
- It does not duplicate daemon packets, projections, source inventory, graph browsing, or search.
- It does not manage Home Assistant long-lived access tokens for the daemon.

The daemon is the source of truth. Home Assistant supplies context, service calls, sensors, repairs, Assist plumbing, and event handling.
