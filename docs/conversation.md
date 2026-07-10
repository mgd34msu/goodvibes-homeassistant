# Conversation agent

The GoodVibes conversation entity is a Home Assistant Assist agent. The model
call and Home Assistant control both run on the GoodVibes daemon — that is the
product. The entity streams each turn to the daemon's remote-chat endpoint and
renders the reply through Home Assistant's `ChatLog` delta-stream API.

Within that boundary, the entity behaves like a first-class conversation agent
by routing Home Assistant's native conversation helper layer into the daemon
call.

## What is adopted

- **Options flow.** The entity exposes the same two settings a built-in
  conversation agent exposes: a custom **prompt** and a selected Home Assistant
  **LLM API** (`llm_hass_api`). They live on the config entry's options and are
  editable after setup without removing the integration.
- **`homeassistant.helpers.llm` prompt assembly.** Every turn calls
  `chat_log.async_provide_llm_data(...)` — the canonical helper first-class
  agents use — with the selected LLM API, the custom prompt, and any per-turn
  `extra_system_prompt`. Home Assistant assembles the system prompt (custom
  instructions, the API prompt, the date/time prompt, and the extra prompt).
- **Forwarding the assembled prompt.** When the user has configured the LLM API
  or a custom prompt, the assembled system prompt travels to the daemon as the
  turn's `instructions`. An unconfigured agent forwards nothing, so the daemon
  keeps its own default behavior (unchanged from before).
- **The exposed-entities boundary.** When an LLM API is selected, the prompt
  Home Assistant assembles lists only the entities exposed to assistants
  (`async_should_expose`). The instructions handed to the daemon therefore honor
  the same boundary as the Home Graph snapshot (see
  [Home Graph reference](home-graph.md)).
- **Native error surfacing.** A misconfigured LLM API id (for example, one that
  was later removed) raises `ConverseError`, which is returned as a native
  conversation result instead of a daemon round-trip.

## What is deliberately not adopted, and why

- **Home Assistant's tool-calling loop / local intent execution.** The selected
  LLM API's tools (`HassTurnOn`, `GetLiveContext`, and so on) are made available
  to the chat log but are **not** executed inside Home Assistant. The daemon runs
  the model and already owns a Home Assistant control surface of its own (the
  `homeassistant` tool channel — `call_service`, `render_template`, and the rest).
  Running Home Assistant's tool loop in parallel would double-execute control
  actions and race the daemon. Tool execution therefore stays on the daemon by
  design; Home Assistant contributes the prompt and the exposed-entity context,
  not a second executor.
- **A local `llm.API` implementation for the daemon to call back into.** The
  daemon reaches Home Assistant through the existing surface described above, so
  registering a parallel callback API here would be redundant.
