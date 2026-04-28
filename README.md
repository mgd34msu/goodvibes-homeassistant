# GoodVibes Home Assistant Integration

Custom Home Assistant integration for the GoodVibes daemon Home Assistant surface from `@pellux/goodvibes-sdk` `0.26.0`.

This integration keeps Home Assistant-specific behavior in Home Assistant:

- config flow for daemon URL, daemon bearer token, webhook secret, and event type
- device registry entry for the GoodVibes daemon
- Assist conversation agent support through the remote-chat `/api/homeassistant/conversation` endpoint
- services for prompts, task-style prompts, status, cancellation, and daemon-exposed HA tools
- Home Graph services that sync HA context into the daemon-owned knowledge/wiki
- local event listener for `goodvibes_message`
- sensors for daemon status, last reply, active session/message/agent IDs, last error, tool catalog status, and Home Graph status

It does not reimplement GoodVibes routing, tool catalogs, provider/model resolution, or agent spawning.
Assist chat stays in isolated daemon remote-chat sessions; it does not use shared TUI sessions, WRFC review/fix chains, or agent task report output.
Home Graph data is stored and rendered by the daemon knowledge/wiki in a space like `homeassistant:<installationId>`.

## Daemon Configuration

Enable the Home Assistant surface in the GoodVibes daemon:

```json
{
  "featureFlags": {
    "homeassistant-surface": "enabled"
  },
  "surfaces": {
    "homeassistant": {
      "enabled": true
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

The Home Assistant long-lived access token belongs in the daemon config as `surfaces.homeassistant.accessToken`. The integration stores the webhook secret so Home Assistant can submit prompts to `/webhook/homeassistant`.

Assist conversation turns use the daemon bearer token and the synchronous daemon endpoint:

```http
POST /api/homeassistant/conversation
Authorization: Bearer <daemon operator token>
```

The webhook endpoint remains for automation/service calls that intentionally want queued async behavior.
Use SDK `0.26.0` or newer for Home Graph support, then restart the daemon after upgrading.

## Installation

Copy `custom_components/goodvibes` into your Home Assistant `custom_components` directory, restart Home Assistant, then add the integration from Settings > Devices & services.

The config flow validates:

- `GET /status`
- `GET /api/homeassistant/health`
- `POST /api/channels/actions/homeassistant/homeassistant-manifest`
- `GET /api/homeassistant/home-graph/status` when Home Graph is enabled

## Assist

After setup, select the GoodVibes conversation entity as the conversation agent in a Home Assistant Assist pipeline. Assist turns are sent to `/api/homeassistant/conversation`, which waits for the final remote-chat response and returns `assistant.speechText` or `assistant.text` directly.

The daemon owns Home Assistant remote-chat sessions and expires idle sessions after `surfaces.homeassistant.remoteSessionTtlMs`, which defaults to 20 minutes. Cancellation uses the daemon remote-chat cancel endpoint with a `sessionId` or `messageId`.

## Services

The integration registers these services:

- `goodvibes.prompt`
- `goodvibes.run_agent`
- `goodvibes.status`
- `goodvibes.cancel`
- `goodvibes.call_tool`
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

Example prompt:

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
  task: Check whether any exterior lights are still on and turn them off if nobody is home.
  provider_id: openai
  model_id: gpt-5.5
  tools:
    - homeassistant_states
    - homeassistant_call_service
```

Example cancellation:

```yaml
action: goodvibes.cancel
data:
  session_id: ha-chat-sess-1234
```

Example daemon-exposed tool call:

```yaml
action: goodvibes.call_tool
data:
  tool: homeassistant_state
  input:
    entityId: light.kitchen
```

## Home Graph

Home Graph is SDK/daemon-owned. This integration collects Home Assistant context and calls daemon APIs; it does not store, search, or render graph data locally.

The default knowledge space is:

```text
homeassistant:<installationId>
```

Example sync:

```yaml
action: goodvibes.sync_home_graph
data: {}
```

Example manual URL ingest linked to a device:

```yaml
action: goodvibes.ingest_url
data:
  url: https://example.com/manual.pdf
  title: Front door lock manual
  target_kind: device
  target_id: front-door-lock
  relation: has_manual
```

Example graph question:

```yaml
action: goodvibes.ask_home_graph
data:
  query: What battery does the front door sensor use?
```

## Event Handling

GoodVibes publishes back into Home Assistant through the Home Assistant REST event bus:

```http
POST /api/events/goodvibes_message
Authorization: Bearer <Home Assistant long-lived access token>
```

The integration listens for `goodvibes_message` by default. If you configure a custom daemon event type, use the same value in the integration config flow.
