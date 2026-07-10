# GoodVibes Documentation

This directory keeps the detailed reference material out of the quickstart README.

- [Home Graph reference](home-graph.md): daemon routes, sync, ingest, linking, Ask, pages, map, refinement, reindex, reset, and examples.
- [Service reference](services.md): Home Assistant services, common fields, examples, and map filters.
- [Conversation agent](conversation.md): how the Assist agent adopts Home Assistant's llm helper layer and what stays on the daemon.
- [Voice: Wyoming → Assist → GoodVibes](voice-assist.md): using the conversation entity as the agent in an Assist pipeline fed by a Wyoming satellite, and what stays with Home Assistant/Wyoming.
- [Causal provenance](causal-provenance.md): attributing a state change to its cause from the Home Assistant context chain, in the Home Graph snapshot and the `causal_chain` service.
- [Habit mining](habits.md): consent-gated local detection of recurring patterns, surfaced as automation proposals you review and accept.
- [Troubleshooting](troubleshooting.md): common setup, auth, Home Graph, Assist, upload, stale state, and reset problems.
- [Known limits](known-limits.md): current operational limits around upload size, stale daemon clients, Home Graph ownership, release delivery, and reset/import boundaries.
- [Security and credentials](security.md): token roles, credential storage, browser upload handling, rotation, and exposure boundaries.
- [SDK compatibility](sdk-compatibility.md): current SDK target, compatibility expectations, and upgrade validation notes.
- [Development and release](development.md): local checks, CI jobs, release metadata, tag workflow, and release archive contents.

The root [README](../README.md) is the install and quickstart guide.
