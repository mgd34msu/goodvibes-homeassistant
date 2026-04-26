# GoodVibes Home Assistant Integration

Custom Home Assistant integration for the GoodVibes daemon Home Assistant surface from `@pellux/goodvibes-sdk` `0.25.11`.

This integration keeps Home Assistant-specific behavior in Home Assistant:

- config flow for daemon URL, daemon bearer token, webhook secret, and event type
- device registry entry for the GoodVibes daemon
- services for prompts, agent tasks, status, cancellation, and daemon-exposed HA tools
- local event listener for `goodvibes_message`
- sensors for daemon status, last reply, active session/agent IDs, last error, and tool catalog status

It does not reimplement GoodVibes routing, tool catalogs, provider/model resolution, or agent spawning.

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

The Home Assistant long-lived access token belongs in the daemon config as `surfaces.homeassistant.accessToken`. The integration stores the webhook secret so Home Assistant can submit prompts to `/webhook/homeassistant`.

## Installation

Copy `custom_components/goodvibes` into your Home Assistant `custom_components` directory, restart Home Assistant, then add the integration from Settings > Devices & services.

The config flow validates:

- `GET /status`
- `POST /api/channels/actions/homeassistant/homeassistant-manifest`

## Services

The integration registers these services:

- `goodvibes.prompt`
- `goodvibes.run_agent`
- `goodvibes.status`
- `goodvibes.cancel`
- `goodvibes.call_tool`

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

Example agent task:

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

Example daemon-exposed tool call:

```yaml
action: goodvibes.call_tool
data:
  tool: homeassistant_state
  input:
    entityId: light.kitchen
```

## Event Handling

GoodVibes publishes back into Home Assistant through the Home Assistant REST event bus:

```http
POST /api/events/goodvibes_message
Authorization: Bearer <Home Assistant long-lived access token>
```

The integration listens for `goodvibes_message` by default. If you configure a custom daemon event type, use the same value in the integration config flow.
