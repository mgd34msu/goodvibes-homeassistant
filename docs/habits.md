# Habit mining — recurring-pattern proposals, never silent rules

When you opt in, the integration keeps a bounded, in-memory record of its own
observed state changes and periodically runs a local frequency analysis over it.
Recurring patterns — "this controllable entity tends to change to this state at
about this time on weekdays" — are surfaced as automation **proposals** for you
to review. Nothing is ever created silently, and no observation data leaves the
machine.

## Turning it on

Habit mining is **off by default**. Enable it in the integration's options
(*Settings → Devices & services → GoodVibes → Configure*), which Home Assistant
restricts to administrators:

- **Enable habit mining (proposals only)** — the switch that starts the local
  analysis.
- **Habit observation retention (days)** — how long an observation is kept in
  memory before it is pruned (1–60 days; default 14).

## Honest boundaries

- **In-memory only.** Observations are held in a buffer capped by both age (the
  retention days) and count. They are **not** written to disk and do **not**
  survive a restart, so proposals reflect only the retained window. This is
  stated plainly rather than pretending to mine a long history.
- **Proposals only.** A proposal carries a ready-to-use standard Home Assistant
  automation config, but it is created only when you explicitly accept it.
- **Actionable only.** A proposal is generated only for an entity whose observed
  state maps to a safe, well-understood service (light/switch/fan/input_boolean
  on/off, cover open/close, lock lock/unlock, …). Sensor readings and other
  non-controllable states are never turned into control automations.
- **Same exposure boundary.** Only entities exposed to assistants are observed
  (unless the entry opts into unexposed entities), matching the rest of the
  integration.

## How a pattern becomes a proposal

The analysis groups observed changes by entity, target state, day type
(weekday/weekend), and a 30-minute time-of-day bucket. A group becomes a proposal
only when it recurs on at least 3 distinct calendar days and at least 3 times
inside the retained window. Each proposal includes a plain-language description,
the observed count and day span, and a standard automation config with a `time`
trigger, a `weekday` condition, and the reproducing service call.

When proposals exist, an informational repair notification points you at the
review services below.

## Reviewing and accepting

List the current proposals (read-only):

```yaml
action: goodvibes.habit_proposals
```

Each proposal has a `proposalId`, a `description`, and the proposed `automation`
config. To create one as a real automation — **admin-gated and
confirmation-gated** — accept it explicitly:

```yaml
action: goodvibes.accept_habit
data:
  proposal_id: <proposalId from habit_proposals>
  confirm: CREATE
```

`accept_habit` appends the automation to Home Assistant's default UI automation
store (`automations.yaml`) and reloads the `automation` integration — the same
path Home Assistant's own automation editor uses. Without `confirm: CREATE`,
nothing is created. Accepting the same proposal twice is refused. After it is
created, review and adjust it like any other automation before relying on it.
