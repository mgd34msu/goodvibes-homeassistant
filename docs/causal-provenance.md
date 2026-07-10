# Causal provenance — "why did the light turn on at 3am?"

Home Assistant threads a **context** through everything it does. Every state
change, service call, automation run, and script run carries a context with an
`id`, an optional `parent_id` that links an effect to the thing that caused it,
and an optional `user_id` when a person is behind it. Home Assistant's own
logbook uses exactly this chain to attribute events.

This integration builds a small, bounded, in-memory index of that chain so it can
answer cause questions about the home. The provenance travels two ways: it
enriches the Home Graph snapshot the daemon indexes (so the daemon's grounding
`ask` path can answer cause questions), and it is queryable directly through the
`goodvibes.causal_chain` service.

## What the context chain genuinely provides vs. what is unknowable

For each tracked state change, the attributed cause is one of:

| Cause `kind`            | Meaning                                                                 |
| ----------------------- | ----------------------------------------------------------------------- |
| `automation`            | An automation run caused the change (chained through `parent_id`).      |
| `script`                | A script run caused the change.                                         |
| `scene`                 | A scene being applied (`scene.turn_on`) caused the change.              |
| `service_call`          | A service call caused it, and no automation/script/scene was above it.  |
| `user`                  | The change's context carries a `user_id` — a person did it.             |
| `device_or_integration` | A **root** context with no parent and no user: the entity/integration reported the change itself (a device report or a poll). |
| `unknown`               | The change has a parent context this tracker never captured (for example, it happened before Home Assistant started). The chain is broken, so guessing is refused. |

This honesty is deliberate. Home Assistant does **not** record *which*
integration produced a `device_or_integration` change in the context, so the
integration does not invent one; and a broken chain is reported as `unknown`
rather than attributed to the nearest thing that happens to be lying around.

The indexes are recent-history caches bounded by count — not a full audit log —
and they start empty when the integration (re)starts.

## In the Home Graph snapshot

When Home Graph is enabled, each entity in the synced snapshot carries a
`provenance` object (and a mirrored `metadata.cause`) describing what caused its
current state. Because the daemon grounds conversation turns in the registered
graph, "why did the porch light turn on?" can be answered from the graph without
the integration re-deriving anything per turn. Older daemons that do not
understand the field simply ignore it.

## The `causal_chain` service

`goodvibes.causal_chain` returns the attributed cause for an entity's recent
state changes and its current state. It is **admin-gated** and additionally
checks the caller's control permission for the target entity, matching the other
state-touching services.

```yaml
action: goodvibes.causal_chain
data:
  entity_id: light.porch
  limit: 10
```

The response contains the entity's `current` state with its provenance, a
`changes` list (each with `from`, `to`, `changedAt`, and a resolved
`provenance`), and a `note` stating plainly that the history is in-memory since
the integration last started. Any `user_id` in the chain is resolved to a
display name where Home Assistant can provide one.
