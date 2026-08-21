# Known limits

These limits describe the current integration and daemon contract. They are operational constraints, not intended product boundaries.

## Thin client boundary

The integration does not store, search, or repair Home Graph data locally. The daemon owns:

| Capability | Covered in |
| --- | --- |
| Knowledge storage | [home-graph.md](home-graph.md) (Daemon routes, Workflow) |
| Artifact storage and extraction | [home-graph.md](home-graph.md#ingest) |
| Source classification | [home-graph.md](home-graph.md#workflow) |
| Semantic enrichment | [home-graph.md](home-graph.md#reindex-and-refinement) |
| Fact and issue generation | [home-graph.md](home-graph.md#review) |
| Answer synthesis | [home-graph.md](home-graph.md#ask) |
| Generated pages | [home-graph.md](home-graph.md#pages) |
| Packets | [services.md](services.md#ask-pages-and-packets) |
| Visual map layout | [home-graph.md](home-graph.md#map) |
| Export, import, reset, and reindex behavior | [home-graph.md](home-graph.md#export-import-and-reset) |

If Home Graph answers, pages, issues, or map output look wrong, fix or reset the daemon-owned knowledge space rather than adding local Home Assistant inference.

## Upload size and timeouts

The GoodVibes SDK (validated against `1.3.0`) defaults daemon artifact storage to `512 MiB` through `storage.artifacts.maxBytes`. This integration also refuses a panel upload larger than `512 MiB` before buffering it to local disk, so an oversized file is rejected up front instead of filling the temporary filesystem.

Large uploads can still fail before they reach the daemon because of:

- Home Assistant request size limits
- Reverse proxy body size limits
- Reverse proxy read/write timeouts
- Network interruptions between browser, Home Assistant, and daemon
- Daemon extraction/indexing time

Use the sidebar multipart upload path for browser uploads. Do not base64 large PDFs, manuals, receipts, or photos into JSON.

URL, note, artifact, import, reindex, and refinement calls allow up to one hour for daemon extraction/indexing. Sync-generated pages, packets, and exports allow up to ten minutes.

## Stale daemon clients

After upgrading or restarting the GoodVibes daemon SDK during live validation, restart Home Assistant after the daemon reports healthy. This forces the integration to reopen its daemon client.

Symptoms of stale runtime state include:

- Assist still failing after a daemon-side fix.
- Home Graph status not reflecting the updated daemon.
- Ask, Pages, or Map showing stale behavior after an SDK upgrade.
- Upload or reindex calls using old timeout or response expectations.

## Home Graph reset versus import

Export/import are for backup and transfer. They are not a reset substitute.

Use `goodvibes.home_graph_reset` when recovering from bad historical ingest, bad links, bad generated pages, or contaminated review state. Preview first with `dry_run: true`; destructive reset requires `confirm: RESET`.

Do not manually delete SDK database rows from the integration side.

## Release delivery

The Home Assistant update entity installs GitHub release assets named `goodvibes.zip`. A commit pushed to `main` is not automatically a release.

Release delivery requires:

- Version metadata updated in `manifest.json` and `const.py`.
- A tag in the form `v<manifest version>`.
- A successful release workflow that uploads `goodvibes.zip`.

Docs-only commits can remain unreleased unless the documentation should be included in a new release asset.

## Home Assistant restart required after update

After installing an integration update through Home Assistant, restart Home Assistant so new Python modules and frontend files load.

Reloading the config entry is not enough for all Python and frontend changes.

## Browser token exposure

The browser panel must not receive the daemon bearer token. Browser requests go through Home Assistant-authenticated websocket and upload endpoints, and Home Assistant forwards daemon calls server-side.

Any feature requiring direct browser-to-daemon calls needs a separate scoped browser-safe daemon credential flow before it can be implemented safely.

## Service schema detail

The human-readable service guide summarizes behavior. Home Assistant selector-level field definitions live in `custom_components/goodvibes/services.yaml`.

When service fields change, update both the schema and docs. The integration should continue accepting these documented compatibility aliases (from `services.yaml`):

| Alias | Canonical field |
| --- | --- |
| `url` | `uri` (the artifact URI) |
| `fact_id` | `issue_id` |
| `decision` | `action` |
