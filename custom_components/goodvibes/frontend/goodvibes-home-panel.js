/*! GoodVibes Home Assistant goodvibes-home-panel.js v0.9.0
 * Built from frontend/src/goodvibes-home-panel.js by frontend/build.mjs — do not edit the
 * served artifact directly; edit the source and rebuild. */


// src/goodvibes-home-panel.js
var DEFAULT_WS_TYPE = "goodvibes/home_graph/call";
var DEFAULT_UPLOAD_URL = "/api/goodvibes/home-graph/upload";
var AUTO_TRIAGE_BATCH_LIMIT = 25;
var OPEN_ISSUES_PAYLOAD = { status: "open" };
var ACTIVE_REFINEMENT_STATES = /* @__PURE__ */ new Set([
  "queued",
  "searching",
  "evaluating",
  "extracting",
  "applying",
  "verifying"
]);
var TARGET_KIND_OPTIONS = [
  "",
  "ha_entity",
  "ha_device",
  "ha_area",
  "ha_room",
  "ha_automation",
  "ha_script",
  "ha_scene",
  "ha_label",
  "ha_integration",
  "ha_device_passport",
  "ha_maintenance_item",
  "ha_troubleshooting_case",
  "ha_purchase",
  "ha_network_node",
  "source",
  "node"
];
var RELATION_OPTIONS = [
  "",
  "source_for",
  "has_manual",
  "has_receipt",
  "has_warranty",
  "has_issue",
  "fixed_by",
  "uses_battery",
  "located_in",
  "controls",
  "belongs_to_device",
  "connected_via",
  "part_of_network",
  "mentioned_by"
];
var MAP_HA_FILTERS = [
  ["objectKinds", "Objects"],
  ["automations", "Automations"],
  ["areaIds", "Areas"],
  ["integrationDomains", "Integrations"],
  ["domains", "Domains"],
  ["deviceClasses", "Device Classes"],
  ["labels", "Labels"],
  ["entityIds", "Entities"],
  ["deviceIds", "Devices"],
  ["integrationIds", "Integration IDs"]
];
var MAP_FILTER_GROUPS = [
  { key: "entityIds", alias: "automations", label: "Automations", match: (value) => String(value || "").startsWith("automation."), defaultOpen: true },
  { key: "areaIds", label: "Areas", defaultOpen: true },
  { key: "integrationDomains", label: "Integrations", defaultOpen: true },
  { key: "domains", label: "Domains", defaultOpen: true },
  { key: "objectKinds", label: "Objects" },
  { key: "entityIds", label: "Entities", match: (value) => !String(value || "").startsWith("automation.") },
  { key: "deviceIds", label: "Devices", technical: true },
  { key: "deviceClasses", label: "Device Classes" },
  { key: "labels", label: "Labels", noisy: true },
  { key: "integrationIds", label: "Integration IDs", technical: true }
];
var MAP_DEFAULT_LIMIT = 150;
var MAP_VISIBLE_FACET_LIMIT = 14;
var MAP_DEFAULT_OPEN_FILTERS = /* @__PURE__ */ new Set([
  "objectKinds",
  "automations",
  "areaIds",
  "integrationDomains",
  "domains"
]);
var MAP_TECHNICAL_FILTERS = /* @__PURE__ */ new Set(["entityIds", "deviceIds", "integrationIds"]);
var GoodVibesHomePanel = class extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "browse";
    this._busy = "";
    this._error = "";
    this._status = {};
    this._sources = {};
    this._pages = {};
    this._selectedPageKey = "";
    this._refinement = {};
    this._refinementState = "";
    this._refinementLimit = 100;
    this._browse = {};
    this._map = {};
    this._issues = {};
    this._answer = {};
    this._lastResult = {};
    this._filter = "";
    this._mapLimit = MAP_DEFAULT_LIMIT;
    this._mapQuery = "";
    this._mapFacetQuery = "";
    this._mapIncludeSources = false;
    this._mapIncludeIssues = false;
    this._mapIncludeGenerated = false;
    this._mapFilters = {};
    this._loaded = false;
    this._pendingBackgroundRender = false;
    this._selectedReviewIds = /* @__PURE__ */ new Set();
    this._reviewAction = "reject";
    this._reviewNote = "";
    this._lastTriageSignature = "";
    this._triageInFlight = false;
    this._triageQueued = false;
    this._triageSummary = null;
    this._triageProgress = null;
    this._triageSeenIssueIds = /* @__PURE__ */ new Set();
    this.shadowRoot.addEventListener("focusout", () => {
      queueMicrotask(() => this._flushPendingBackgroundRender());
    });
  }
  set hass(hass) {
    const hadHass = Boolean(this._hass);
    this._hass = hass;
    if (!this._loaded && hass) {
      this._loaded = true;
      this._refreshAll({ background: true });
    }
    if (!hadHass) {
      this._render();
    }
  }
  get hass() {
    return this._hass;
  }
  set panel(panel) {
    this._panel = panel;
  }
  get _wsType() {
    return this._panel?.config?.wsType || DEFAULT_WS_TYPE;
  }
  get _uploadUrl() {
    return this._panel?.config?.uploadUrl || DEFAULT_UPLOAD_URL;
  }
  get _configEntryId() {
    return this._panel?.config?.configEntryId || "";
  }
  connectedCallback() {
    this._render();
  }
  async _refreshAll(options = {}) {
    await this._call("status", {}, { quiet: true });
    await Promise.all([
      this._call("sources", {}, { quiet: true }),
      this._call("browse", {}, { quiet: true }),
      this._call("issues", OPEN_ISSUES_PAYLOAD, { quiet: true }),
      this._call("refinement_tasks", { limit: this._refinementLimit }, { quiet: true })
    ]);
    if (this._tab === "map") {
      await this._call("map", this._mapPayload(), { quiet: true });
    }
    if (this._tab === "pages") {
      await this._call("pages", { limit: 250, includeMarkdown: true }, { quiet: true });
    }
    if (options.background) {
      this._renderAfterBackgroundUpdate();
    } else {
      this._render();
    }
    if (!this._error && options.triage !== false) {
      this._queueAutoTriage(options);
    }
  }
  async _call(action, payload = {}, options = {}) {
    if (!this._hass) {
      return {};
    }
    this._error = "";
    if (!options.quiet) {
      this._busy = action;
      this._render();
    }
    try {
      const result = await this._hass.callWS({
        type: this._wsType,
        action,
        config_entry_id: this._configEntryId || void 0,
        payload
      });
      if (!options.quiet || options.recordResult) {
        this._lastResult = result || {};
      }
      if (action === "status") {
        this._status = result || {};
      } else if (action === "sources") {
        this._sources = result || {};
      } else if (action === "pages") {
        this._pages = result || {};
      } else if (action === "refinement_tasks") {
        this._refinement = result || {};
      } else if (action === "browse") {
        this._browse = result || {};
      } else if (action === "map") {
        this._map = result || {};
      } else if (action === "issues") {
        this._issues = result || {};
      } else if (action === "ask") {
        this._answer = result || {};
      }
      return result || {};
    } catch (err) {
      const message = err?.message || String(err);
      if (!options.suppressError) {
        this._error = message;
      }
      if (options.recordResult) {
        this._lastResult = { ok: false, action, error: message };
      }
      return { ok: false, action, error: message };
    } finally {
      if (!options.quiet) {
        this._busy = "";
        this._render();
      }
    }
  }
  async _upload(form, options = {}) {
    const fields = this._formValues(form);
    const input = form.querySelector('input[name="file"]');
    const file = input?.files?.[0];
    if (!file) {
      this._showError(new Error("Choose a file to upload."));
      return;
    }
    const data = new FormData();
    data.append("file", file, file.name);
    this._appendFormField(data, "config_entry_id", this._configEntryId);
    this._appendFormField(data, "title", fields.title);
    this._appendFormField(data, "tags", this._tagsFromText(fields.tags));
    this._appendFormField(data, "target", this._targetFromFields(fields));
    this._appendFormField(data, "metadata", this._jsonFromText(fields.metadata));
    if (fields.allowPrivateHosts) {
      data.append("allowPrivateHosts", "true");
    }
    this._busy = "upload";
    this._error = "";
    this._render();
    try {
      const result = await this._postUpload(data);
      this._lastResult = result || {};
      if (!options.skipRefresh) {
        await this._syncAndRefresh();
      }
      return result || {};
    } catch (err) {
      this._showError(err);
      return {};
    } finally {
      this._busy = "";
      this._render();
    }
  }
  async _postUpload(data) {
    const options = {
      method: "POST",
      body: data,
      credentials: "same-origin"
    };
    const token = this._hass?.auth?.data?.access_token;
    if (token && !this._hass?.fetchWithAuth) {
      options.headers = { Authorization: `Bearer ${token}` };
    }
    const response = this._hass?.fetchWithAuth ? await this._hass.fetchWithAuth(this._uploadUrl, options) : await fetch(this._uploadUrl, options);
    const payload = await response.json();
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.error || `Upload failed: ${response.status}`);
    }
    return payload;
  }
  _wireEvents() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        this._tab = button.dataset.tab;
        this._render();
        if (this._tab === "map" && !itemsFromPayload(this._map, ["nodes"]).length) {
          this._call("map", this._mapPayload()).catch((err) => this._showError(err));
        }
        if (this._tab === "pages") {
          this._call("pages", { limit: 250, includeMarkdown: true }).catch(
            (err) => this._showError(err)
          );
        }
        if (this._tab === "refine") {
          this._call(
            "refinement_tasks",
            this._compact({ limit: this._refinementLimit, state: this._refinementState })
          ).catch((err) => this._showError(err));
        }
      });
    });
    root.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", () => {
        this._handleAction(button.dataset.action, button).catch((err) => this._showError(err));
      });
    });
    root.querySelectorAll("[data-map-filter-key]").forEach((button) => {
      button.addEventListener("click", () => {
        this._toggleMapFilter(
          button.dataset.mapFilterKey || "",
          button.dataset.mapFilterValue || ""
        ).catch((err) => this._showError(err));
      });
    });
    root.querySelectorAll("[data-select-issue]").forEach((button) => {
      button.addEventListener("click", () => {
        this._toggleReviewSelection(button.dataset.selectIssue || "");
        this._render();
      });
    });
    root.querySelectorAll("form[data-form]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._handleForm(form).catch((err) => this._showError(err));
      });
    });
  }
  async _handleAction(action, element) {
    if (action === "refresh") {
      await this._refreshAll();
      return;
    }
    if (action === "sync") {
      await this._call("sync");
      await this._refreshAll();
      return;
    }
    if (action === "reindex") {
      await this._call("reindex");
      await this._refreshAll();
      return;
    }
    if (action === "refinement_refresh") {
      await this._call(
        "refinement_tasks",
        this._compact({ limit: this._refinementLimit, state: this._refinementState })
      );
      return;
    }
    if (action === "refinement_run") {
      await this._call("refinement_run", { limit: 25 });
      await this._refreshAll({ triage: false });
      return;
    }
    if (action === "refinement_cancel") {
      const id = element?.dataset?.taskId || "";
      await this._call("refinement_cancel", { id });
      await this._refreshAll({ triage: false });
      return;
    }
    if (action === "map_clear_filters") {
      this._mapFilters = {};
      await this._call("map", this._mapPayload());
      return;
    }
    if (action === "page_select") {
      this._selectedPageKey = element?.dataset?.pageKey || "";
      this._render();
      return;
    }
    if (action === "page_map_filter") {
      const key = element?.dataset?.mapFilterKey || "";
      const value = element?.dataset?.mapFilterValue || "";
      if (key && value) {
        this._mapFilters = { ...this._mapFilters, [key]: [value] };
        this._tab = "map";
        await this._call("map", this._mapPayload());
      }
      return;
    }
    if (action === "page_map_query") {
      const query = element?.dataset?.mapQuery || "";
      if (query) {
        this._mapQuery = query;
        this._tab = "map";
        await this._call("map", this._mapPayload());
      }
      return;
    }
    if (action === "map_clear_facet_search") {
      this._mapFacetQuery = "";
      this._render();
      return;
    }
    if (action === "review_select_all") {
      this._visibleIssues().forEach((issue) => this._selectedReviewIds.add(issueKey(issue)));
      this._render();
      return;
    }
    if (action === "review_run_triage") {
      this._lastTriageSignature = "";
      await this._autoTriageReviewQueue({ force: true, manual: true });
      this._render();
      return;
    }
    if (action === "review_clear") {
      this._selectedReviewIds.clear();
      this._render();
    }
  }
  async _syncAndRefresh() {
    const result = await this._call("sync", {}, { quiet: true, recordResult: true });
    if (this._error || result?.ok === false) {
      this._error = this._error || result?.error || "Home Graph sync failed";
      this._render();
      return;
    }
    await this._refreshAll();
  }
  async _handleForm(form) {
    const name = form.dataset.form;
    const fields = this._formValues(form);
    if (name === "ask") {
      await this._call("ask", this._compact({
        query: fields.query,
        limit: fields.limit,
        mode: fields.mode,
        includeSources: fields.includeSources,
        includeConfidence: fields.includeConfidence,
        includeLinkedObjects: fields.includeLinkedObjects
      }));
      return;
    }
    if (name === "browse") {
      this._filter = fields.query || "";
      await this._call("browse", { limit: fields.limit || 250 });
      return;
    }
    if (name === "map") {
      this._mapLimit = Number(fields.limit) || MAP_DEFAULT_LIMIT;
      this._mapQuery = fields.query || "";
      this._mapIncludeSources = Boolean(fields.includeSources);
      this._mapIncludeIssues = Boolean(fields.includeIssues);
      this._mapIncludeGenerated = Boolean(fields.includeGenerated);
      await this._call("map", this._mapPayload());
      return;
    }
    if (name === "map_facet_search") {
      this._mapFacetQuery = fields.facetQuery || "";
      this._render();
      return;
    }
    if (name === "refinement") {
      this._refinementLimit = Number(fields.limit) || 100;
      this._refinementState = fields.state || "";
      await this._call(
        "refinement_tasks",
        this._compact({ limit: this._refinementLimit, state: this._refinementState })
      );
      return;
    }
    if (name === "refinement_run") {
      await this._call(
        "refinement_run",
        this._compact({
          limit: fields.limit,
          force: fields.force,
          gapIds: this._tagsFromText(fields.gapIds),
          sourceIds: this._tagsFromText(fields.sourceIds)
        })
      );
      await this._refreshAll({ triage: false });
      return;
    }
    if (name === "url") {
      await this._call("ingest_url", this._ingestPayload(fields, { url: fields.url }));
      if (!this._error) {
        await this._syncAndRefresh();
      }
      return;
    }
    if (name === "note") {
      await this._call(
        "ingest_note",
        this._ingestPayload(fields, {
          body: fields.body
        })
      );
      if (!this._error) {
        await this._syncAndRefresh();
      }
      return;
    }
    if (name === "artifact") {
      await this._call(
        "ingest_artifact",
        this._ingestPayload(fields, {
          artifactId: fields.artifactId,
          path: fields.path,
          uri: fields.uri
        })
      );
      if (!this._error) {
        await this._syncAndRefresh();
      }
      return;
    }
    if (name === "upload") {
      await this._upload(form);
      return;
    }
    if (name === "review_upload_source") {
      const result = await this._upload(form, { skipRefresh: true });
      if (!this._error) {
        await this._resolveReviewIssueWithSource(fields, result);
      }
      return;
    }
    if (name === "review_url_source") {
      const result = await this._call(
        "ingest_url",
        this._reviewSourcePayload(fields, { url: fields.url })
      );
      if (!this._error) {
        await this._resolveReviewIssueWithSource(fields, result);
      }
      return;
    }
    if (name === "review_existing_source") {
      const result = await this._call("link", {
        sourceId: fields.sourceId,
        target: this._targetFromFields(fields),
        metadata: this._jsonFromText(fields.metadata)
      });
      if (!this._error) {
        await this._resolveReviewIssueWithSource(fields, result);
      }
      return;
    }
    if (name === "review_bulk_upload_source") {
      const result = await this._upload(form, { skipRefresh: true });
      if (!this._error) {
        await this._resolveBulkReviewIssuesWithSource(fields, result);
      }
      return;
    }
    if (name === "review_bulk_url_source") {
      const result = await this._call(
        "ingest_url",
        this._reviewSourcePayload(fields, { url: fields.url })
      );
      if (!this._error) {
        await this._resolveBulkReviewIssuesWithSource(fields, result);
      }
      return;
    }
    if (name === "review_bulk_existing_source") {
      await this._resolveBulkReviewIssuesWithSource(fields, {
        sourceId: fields.sourceId
      });
      return;
    }
    if (name === "link" || name === "unlink") {
      await this._call(name, {
        sourceId: fields.sourceId,
        nodeId: fields.nodeId,
        target: this._targetFromFields(fields),
        metadata: this._jsonFromText(fields.metadata)
      });
      if (!this._error) {
        await this._syncAndRefresh();
      }
      return;
    }
    if (name === "review") {
      await this._applyReview(fields);
      return;
    }
    if (name === "page") {
      await this._call(fields.pageType, {
        deviceId: fields.deviceId,
        areaId: fields.areaId,
        roomId: fields.roomId,
        packetKind: fields.packetKind,
        title: fields.title,
        sharingProfile: fields.sharingProfile
      });
      return;
    }
    if (name === "export") {
      await this._call("export");
      return;
    }
    if (name === "import") {
      await this._call("import", {
        data: this._jsonFromText(fields.data)
      });
      return;
    }
    if (name === "reset") {
      if (!fields.dryRun && fields.confirm !== "RESET") {
        this._showError(new Error("Type RESET to reset the Home Graph space."));
        return;
      }
      await this._call("reset", {
        confirm: fields.confirm,
        dryRun: fields.dryRun
      });
      if (!this._error && !fields.dryRun) {
        await this._syncAndRefresh();
      }
    }
  }
  _ingestPayload(fields, extra) {
    return this._compact({
      ...extra,
      title: fields.title,
      tags: this._tagsFromText(fields.tags),
      target: this._targetFromFields(fields),
      metadata: this._jsonFromText(fields.metadata),
      allowPrivateHosts: fields.allowPrivateHosts ? true : void 0
    });
  }
  _reviewSourcePayload(fields, extra) {
    return this._ingestPayload(
      {
        ...fields,
        relation: fields.relation || "has_manual"
      },
      extra
    );
  }
  async _resolveReviewIssueWithSource(fields, sourceResult) {
    const issueId = fields.issueId || "";
    if (!issueId) {
      await this._refreshAll();
      return;
    }
    const sourceId = sourceIdFromResult(fields, sourceResult);
    const relation = fields.relation || "has_manual";
    const review = await this._call(
      "review",
      this._compact({
        issueId,
        action: "resolve",
        value: sourceLinkedReviewValue(sourceId, relation),
        reviewer: "homeassistant"
      }),
      { quiet: true }
    );
    const error = this._error;
    this._lastResult = {
      ok: !error,
      linkedSource: sourceResult,
      review
    };
    if (!error) {
      this._selectedReviewIds.clear();
      await this._syncAndRefresh();
    } else {
      this._render();
    }
  }
  async _resolveBulkReviewIssuesWithSource(fields, sourceResult) {
    const issues = this._selectedIssues(this._visibleIssues()).filter(
      (issue) => isSourceResolvableIssue(issue)
    );
    if (!issues.length) {
      this._showError(new Error("Select one or more missing manual/source issues first."));
      return;
    }
    const sourceId = sourceIdFromResult(fields, sourceResult);
    if (!sourceId) {
      this._showError(new Error("The daemon did not return a source id to link."));
      return;
    }
    const relation = fields.relation || "has_manual";
    this._busy = "review";
    this._error = "";
    this._render();
    const results = [];
    for (const issue of issues) {
      const link = await this._call(
        "link",
        {
          sourceId,
          target: {
            kind: "node",
            id: issue.nodeId,
            relation
          }
        },
        { quiet: true }
      );
      if (this._error) {
        break;
      }
      const review = await this._call(
        "review",
        this._compact({
          issueId: issue.id || issue.issueId,
          nodeId: issue.nodeId,
          action: "resolve",
          value: sourceLinkedReviewValue(sourceId, relation),
          reviewer: "homeassistant"
        }),
        { quiet: true }
      );
      results.push({
        issueId: issue.id || issue.issueId,
        nodeId: issue.nodeId,
        link,
        review
      });
      if (this._error) {
        break;
      }
    }
    const error = this._error;
    this._lastResult = {
      ok: !error,
      sourceId,
      linked: results.length,
      results,
      source: sourceResult
    };
    this._busy = "";
    if (!error) {
      this._selectedReviewIds.clear();
      await this._syncAndRefresh();
    } else {
      this._render();
    }
  }
  _formValues(form) {
    const values = {};
    new FormData(form).forEach((value, key) => {
      if (value instanceof File) {
        return;
      }
      values[key] = typeof value === "string" ? value.trim() : value;
    });
    form.querySelectorAll('input[type="checkbox"]').forEach((input) => {
      values[input.name] = input.checked;
    });
    return values;
  }
  _targetFromFields(fields) {
    if (!fields.targetKind && !fields.targetId) {
      return void 0;
    }
    const target = {
      kind: fields.targetKind,
      id: fields.targetId
    };
    if (fields.relation) {
      target.relation = fields.relation;
    }
    if (fields.targetTitle) {
      target.title = fields.targetTitle;
    }
    return target;
  }
  _appendFormField(formData, key, value) {
    if (value === void 0 || value === null || value === "") {
      return;
    }
    formData.append(key, typeof value === "string" ? value : JSON.stringify(value));
  }
  _jsonFromText(value) {
    if (!value) {
      return void 0;
    }
    return JSON.parse(value);
  }
  _jsonOrText(value) {
    if (!value) {
      return void 0;
    }
    try {
      return JSON.parse(value);
    } catch (_err) {
      return value;
    }
  }
  _tagsFromText(value) {
    if (!value) {
      return void 0;
    }
    return value.split(",").map((tag) => tag.trim()).filter(Boolean);
  }
  _compact(value) {
    return Object.fromEntries(
      Object.entries(value).filter(([, item]) => {
        if (item === void 0 || item === null || item === "") {
          return false;
        }
        if (Array.isArray(item) && item.length === 0) {
          return false;
        }
        return true;
      })
    );
  }
  _mapPayload() {
    const ha = Object.fromEntries(
      Object.entries(this._mapFilters || {}).map(([key, values]) => [key, Array.from(values || []).filter(Boolean)]).filter(([, values]) => values.length)
    );
    return this._compact({
      limit: this._mapLimit,
      query: this._mapQuery,
      includeSources: this._mapIncludeSources,
      includeIssues: this._mapIncludeIssues,
      includeGenerated: this._mapIncludeGenerated,
      ha: Object.keys(ha).length ? ha : void 0
    });
  }
  async _toggleMapFilter(key, value) {
    if (!key || !value) {
      return;
    }
    const values = new Set(this._mapFilters?.[key] || []);
    if (values.has(value)) {
      values.delete(value);
    } else {
      values.add(value);
    }
    this._mapFilters = { ...this._mapFilters, [key]: Array.from(values) };
    if (!values.size) {
      delete this._mapFilters[key];
    }
    await this._call("map", this._mapPayload());
  }
  _showError(err) {
    this._busy = "";
    this._error = err?.message || String(err);
    this._render();
  }
  _renderAfterBackgroundUpdate() {
    if (this._hasActiveOrDirtyForm()) {
      this._pendingBackgroundRender = true;
      return;
    }
    this._render();
  }
  _flushPendingBackgroundRender() {
    if (!this._pendingBackgroundRender || this._hasActiveOrDirtyForm()) {
      return;
    }
    this._render();
  }
  _hasActiveOrDirtyForm() {
    const root = this.shadowRoot;
    if (!root) {
      return false;
    }
    const active = root.activeElement;
    if (isFormControl(active)) {
      return true;
    }
    return Array.from(root.querySelectorAll("input, select, textarea")).some(
      (field) => isDirtyField(field)
    );
  }
  _captureScrollState() {
    const state = /* @__PURE__ */ new Map();
    this.shadowRoot?.querySelectorAll("[data-scroll-region]").forEach((element) => {
      state.set(element.dataset.scrollRegion, {
        left: element.scrollLeft,
        top: element.scrollTop
      });
    });
    return state;
  }
  _restoreScrollState(state) {
    if (!state?.size) {
      return;
    }
    const restore = () => {
      this.shadowRoot?.querySelectorAll("[data-scroll-region]").forEach((element) => {
        const position = state.get(element.dataset.scrollRegion);
        if (!position) {
          return;
        }
        element.scrollLeft = position.left;
        element.scrollTop = position.top;
      });
    };
    restore();
    if (typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(restore);
    }
  }
  _render() {
    if (!this.shadowRoot) {
      return;
    }
    const busy = Boolean(this._busy);
    const busyAttr = busy ? "disabled" : "";
    const scrollState = this._captureScrollState();
    this._pendingBackgroundRender = false;
    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <section class="shell">
        <header class="topbar">
          <div class="identity">
            <span class="logo">
              <ha-icon icon="${escapeAttr(this._panel?.config?.sidebarIcon || "goodvibes:home")}"></ha-icon>
            </span>
            <div>
              <h1>GoodVibes Home</h1>
              <p>${escapeHtml(this._statusLine())}</p>
            </div>
          </div>
          <div class="actions">
            <button type="button" data-action="refresh" title="Refresh" ${busyAttr}>
              <ha-icon icon="mdi:refresh"></ha-icon>
              <span>Refresh</span>
            </button>
            <button type="button" data-action="sync" title="Sync Home Graph" ${busyAttr}>
              <ha-icon icon="mdi:sync"></ha-icon>
              <span>Sync</span>
            </button>
            <button type="button" data-action="reindex" title="Repair Home Graph extraction" ${busyAttr}>
              <ha-icon icon="mdi:file-refresh-outline"></ha-icon>
              <span>Reindex uploads</span>
            </button>
          </div>
        </header>
        <nav class="tabs">
          ${this._tabButton("browse", "mdi:graph-outline", "Browse")}
          ${this._tabButton("map", "mdi:vector-polyline", "Map")}
          ${this._tabButton("ingest", "mdi:tray-arrow-up", "Ingest")}
          ${this._tabButton("ask", "mdi:message-question-outline", "Ask")}
          ${this._tabButton("link", "mdi:link-variant", "Link")}
          ${this._tabButton("refine", "mdi:auto-fix", "Refine")}
          ${this._tabButton("review", "mdi:clipboard-edit-outline", "Review")}
          ${this._tabButton("pages", "mdi:file-document-outline", "Pages")}
        </nav>
        ${this._error ? `<div class="notice error">${escapeHtml(this._error)}</div>` : ""}
        ${this._busy ? this._workingNotice(busyLabel(this._busy)) : ""}
        ${this._tab !== "review" && (this._triageInFlight || this._triageQueued) ? this._triageProgressNotice("GoodVibes is classifying review issues.") : ""}
        <main>
          ${this._renderTab()}
        </main>
      </section>
    `;
    this._wireEvents();
    this._restoreScrollState(scrollState);
  }
  _workingNotice(label) {
    return `
      <div class="notice working">
        <ha-icon class="spin" icon="mdi:loading"></ha-icon>
        <div>
          <strong>${escapeHtml(label)}</strong>
          <small>GoodVibes is working. Long-running graph repair can continue in the background after the request returns.</small>
        </div>
      </div>
    `;
  }
  _tabButton(tab, icon, label) {
    return `
      <button type="button" data-tab="${tab}" class="${this._tab === tab ? "active" : ""}">
        <ha-icon icon="${icon}"></ha-icon>
        <span>${label}</span>
      </button>
    `;
  }
  _renderTab() {
    if (this._tab === "ingest") {
      return this._renderIngest();
    }
    if (this._tab === "map") {
      return this._renderMap();
    }
    if (this._tab === "ask") {
      return this._renderAsk();
    }
    if (this._tab === "link") {
      return this._renderLink();
    }
    if (this._tab === "refine") {
      return this._renderRefinement();
    }
    if (this._tab === "review") {
      return this._renderReview();
    }
    if (this._tab === "pages") {
      return this._renderPages();
    }
    return this._renderBrowse();
  }
  _renderBrowse() {
    const sourceItems = this._filtered(itemsFromPayload(this._sources, ["sources"]));
    const nodes = this._filtered(itemsFromPayload(this._browse, ["nodes"]));
    const edges = this._filtered(itemsFromPayload(this._browse, ["edges"]));
    const issues = this._filtered(itemsFromPayload(this._issues, ["issues"]));
    return `
      <section class="grid two">
        <article class="panel">
          <h2>Home Graph</h2>
          <dl class="facts">
            <div><dt>Status</dt><dd>${escapeHtml(statusValue(this._status.status))}</dd></div>
            <div><dt>Knowledge Space</dt><dd>${escapeHtml(this._status.knowledgeSpaceId || "")}</dd></div>
            <div><dt>Last Sync</dt><dd>${escapeHtml(this._status.lastSyncAt || "")}</dd></div>
            <div><dt>Sources</dt><dd>${escapeHtml(statusCount(this._status, "sourceCount"))}</dd></div>
            <div><dt>Nodes</dt><dd>${escapeHtml(statusCount(this._status, "nodeCount"))}</dd></div>
            <div><dt>Edges</dt><dd>${escapeHtml(statusCount(this._status, "edgeCount"))}</dd></div>
            <div><dt>Issues</dt><dd>${escapeHtml(statusCount(this._status, "issueCount"))}</dd></div>
            <div><dt>Extractions</dt><dd>${escapeHtml(statusCount(this._status, "extractionCount"))}</dd></div>
            <div><dt>Readiness</dt><dd>${escapeHtml(readinessLabel(this._status))}</dd></div>
            <div><dt>Refinement</dt><dd>${escapeHtml(refinementStatusLabel(this._status, this._refinement))}</dd></div>
            <div><dt>Capabilities</dt><dd>${escapeHtml(statusCapabilities(this._status))}</dd></div>
          </dl>
        </article>
        <article class="panel">
          <h2>Filter</h2>
          <form data-form="browse" class="inline-form">
            <label>
              <span>Text</span>
              <input name="query" type="search" autocomplete="off" value="${escapeAttr(this._filter)}">
            </label>
            <label>
              <span>Limit</span>
              <input name="limit" type="number" min="1" max="1000" value="250">
            </label>
            <button type="submit"><ha-icon icon="mdi:magnify"></ha-icon><span>Apply</span></button>
          </form>
        </article>
      </section>
      <section class="grid two">
        ${this._listPanel("Sources", sourceItems)}
        ${this._listPanel("Nodes", nodes)}
        ${this._listPanel("Edges", edges)}
        ${this._listPanel("Issues", issues)}
      </section>
      ${this._resultPanel()}
    `;
  }
  _renderMap() {
    const map = this._map?.result || this._map || {};
    const nodes = itemsFromPayload(map, ["nodes"]);
    const edges = itemsFromPayload(map, ["edges"]);
    const facets = map?.facets?.homeAssistant || {};
    const labelIndex = mapLabelIndex(map);
    const selectedFilters = Object.values(this._mapFilters || {}).reduce(
      (total, values) => total + (Array.isArray(values) ? values.length : 0),
      0
    );
    return `
      <section class="grid">
        <article class="panel map-panel">
          <div class="panel-heading">
            <h2>${escapeHtml(map.title || "Knowledge Map")}</h2>
            <form data-form="map" class="map-form">
              <label>
                <span>Search</span>
                <input name="query" type="search" autocomplete="off" value="${escapeAttr(this._mapQuery)}">
              </label>
              <label>
                <span>Limit</span>
                <input name="limit" type="number" min="1" max="2000" value="${escapeAttr(String(this._mapLimit))}">
              </label>
              <label class="check">
                <input name="includeSources" type="checkbox" ${this._mapIncludeSources ? "checked" : ""}>
                <span>Sources</span>
              </label>
              <label class="check">
                <input name="includeIssues" type="checkbox" ${this._mapIncludeIssues ? "checked" : ""}>
                <span>Issues</span>
              </label>
              <label class="check">
                <input name="includeGenerated" type="checkbox" ${this._mapIncludeGenerated ? "checked" : ""}>
                <span>Pages</span>
              </label>
              <button type="submit"><ha-icon icon="mdi:vector-polyline"></ha-icon><span>Update</span></button>
            </form>
          </div>
          <div class="map-workspace">
            <aside class="map-filters">
              <div class="map-filter-heading">
                <span>${escapeHtml(String(selectedFilters))} selected</span>
                <button type="button" data-action="map_clear_filters">Clear filters</button>
              </div>
              <form data-form="map_facet_search" class="facet-search">
                <label>
                  <span>Find Filter</span>
                  <input name="facetQuery" type="search" autocomplete="off" value="${escapeAttr(this._mapFacetQuery)}" placeholder="Automation, room, entity, device">
                </label>
                <button type="submit"><ha-icon icon="mdi:magnify"></ha-icon><span>Find</span></button>
                ${this._mapFacetQuery ? `<button type="button" data-action="map_clear_facet_search">Clear</button>` : ""}
              </form>
              ${this._selectedMapFilters(labelIndex)}
              ${this._mapFacetGroups(facets, map, labelIndex)}
            </aside>
            <div class="map-main">
              <div class="map-canvas">
                ${this._mapVisual(map, nodes, edges)}
              </div>
              <div class="map-stats">
                <span>${escapeHtml(String(map.nodeCount ?? nodes.length))} nodes</span>
                <span>${escapeHtml(String(map.edgeCount ?? edges.length))} edges</span>
                ${map.totalNodeCount !== void 0 ? `<span>${escapeHtml(String(map.totalNodeCount))} matching records</span>` : ""}
                ${map.spaceId ? `<span>${escapeHtml(map.spaceId)}</span>` : ""}
              </div>
            </div>
          </div>
        </article>
      </section>
      ${this._resultPanel()}
    `;
  }
  _mapFacetGroups(facets, map, labelIndex) {
    const groups = MAP_FILTER_GROUPS.map((group) => this._mapFacetGroup(group, facets?.[group.key], map, labelIndex)).filter(Boolean);
    return groups.length ? groups.join("") : `<p class="empty">No map filters available</p>`;
  }
  _mapFacetGroup(group, values, map, labelIndex) {
    const key = group.key;
    const label = group.label;
    const groupId = group.alias || key;
    const localQuery = this._mapFacetQuery.trim().toLowerCase();
    const selected = this._mapFilters?.[key] || [];
    const baseItems = facetItems(values, key, labelIndex).filter((item) => !group.match || group.match(item.value, item));
    const known = new Set(baseItems.map((item) => item.value));
    const selectedItems = selected.filter((value) => !known.has(value) && (!group.match || group.match(value))).map((value) => enrichFacetItem({ value, label: friendlyFacetLabel(value), count: 0 }, key, labelIndex));
    const selectedKnownItems = baseItems.filter((item) => selected.includes(item.value));
    const selectedValues = new Set(
      [...selectedItems, ...selectedKnownItems].map((item) => item.value)
    );
    const visibleBaseItems = baseItems.filter((item) => shouldShowFacetItem(key, item, group)).filter((item) => !localQuery || facetSearchText(item, key).includes(localQuery));
    const hiddenTechnicalCount = baseItems.length - visibleBaseItems.length;
    const topItems = visibleBaseItems.filter((item) => !selectedValues.has(item.value)).slice(0, MAP_VISIBLE_FACET_LIMIT);
    const items = [...selectedItems, ...selectedKnownItems, ...topItems];
    if (!items.length && (!baseItems.length || localQuery)) {
      return "";
    }
    const open = selected.length || MAP_DEFAULT_OPEN_FILTERS.has(groupId) || group.defaultOpen || localQuery;
    const detail = selected.length ? `${selected.length} selected` : `${baseItems.length} available`;
    return `
      <details class="facet-group ${MAP_TECHNICAL_FILTERS.has(key) || group.technical ? "technical" : ""}" ${open ? "open" : ""}>
        <summary>
          <span>${escapeHtml(label)}</span>
          <small>${escapeHtml(detail)}</small>
        </summary>
        ${items.length ? `<div class="facet-buttons">${items.map((item) => this._mapFacetChip(key, item)).join("")}</div>` : `<p class="facet-note">${escapeHtml(`${hiddenTechnicalCount || baseItems.length} unlabeled technical ID${(hiddenTechnicalCount || baseItems.length) === 1 ? "" : "s"} hidden`)}</p>`}
        ${hiddenTechnicalCount && items.length ? `<p class="facet-note">${escapeHtml(`${hiddenTechnicalCount} unlabeled technical ID${hiddenTechnicalCount === 1 ? "" : "s"} hidden`)}</p>` : ""}
      </details>
    `;
  }
  _mapFacetChip(key, item) {
    const active = (this._mapFilters?.[key] || []).includes(item.value);
    return `
      <button
        type="button"
        class="facet-chip ${active ? "active" : ""}"
        data-map-filter-key="${escapeAttr(key)}"
        data-map-filter-value="${escapeAttr(item.value)}"
        title="${escapeAttr(item.value)}"
      >
        <span>${escapeHtml(item.label || friendlyFacetLabel(item.value))}</span>
        ${item.count !== void 0 ? `<strong>${escapeHtml(String(item.count))}</strong>` : ""}
      </button>
    `;
  }
  _selectedMapFilters(labelIndex) {
    const entries = Object.entries(this._mapFilters || {}).flatMap(
      ([key, values]) => (Array.isArray(values) ? values : []).map((value) => ({ key, value }))
    );
    if (!entries.length) {
      return "";
    }
    return `
      <div class="selected-filters">
        ${entries.map(
      ({ key, value }) => `
              <button
                type="button"
                class="facet-chip active"
                data-map-filter-key="${escapeAttr(key)}"
                data-map-filter-value="${escapeAttr(value)}"
                title="${escapeAttr(value)}"
              >
                <span>${escapeHtml(`${selectedMapFilterLabel(key, value)}: ${displayFacetValue(key, value, labelIndex)}`)}</span>
              </button>
            `
    ).join("")}
      </div>
    `;
  }
  _mapVisual(map, nodes, edges) {
    if (typeof map?.svg === "string" && map.svg && edges.length) {
      return `<img class="map-image" alt="Home Graph knowledge map" src="${escapeAttr(svgDataUrl(map.svg))}">`;
    }
    if (!nodes.length) {
      return `<p class="empty">No map loaded</p>`;
    }
    if (!edges.length) {
      return `
        <div class="map-empty">
          <ha-icon icon="mdi:vector-polyline-remove"></ha-icon>
          <strong>No relationships in this view</strong>
          <span>Select an automation, entity, device, room, or integration from the drilldown filters, or enable Sources/Pages when you want source relationships.</span>
        </div>
      `;
    }
    return `<p class="empty">The daemon did not return a rendered map.</p>`;
  }
  _queueAutoTriage(options = {}) {
    if (this._triageInFlight || this._triageQueued || !this._hass) {
      return;
    }
    const issues = itemsFromPayload(this._issues, ["issues"]);
    if (!issues.length) {
      this._triageSummary = null;
      this._lastTriageSignature = "";
      return;
    }
    const signature = issues.map((issue) => issueKey(issue)).sort().join("|");
    if (!options.force && signature && signature === this._lastTriageSignature) {
      return;
    }
    this._lastTriageSignature = signature;
    if (!options.continuation) {
      const total = this._issueTotal() || issues.length;
      this._triageSeenIssueIds = /* @__PURE__ */ new Set();
      this._triageProgress = {
        total,
        processed: 0,
        reviewed: 0,
        remaining: total,
        batches: 0,
        insight: ""
      };
    }
    this._triageQueued = true;
    window.setTimeout(() => {
      this._triageQueued = false;
      this._autoTriageReviewQueue({ ...options, background: true }).catch((err) => {
        this._triageSummary = { ok: false, error: err?.message || String(err) };
        this._renderAfterBackgroundUpdate();
      });
    }, 0);
  }
  async _autoTriageReviewQueue(options = {}) {
    if (this._triageInFlight || !this._hass) {
      return;
    }
    const issues = itemsFromPayload(this._issues, ["issues"]);
    if (!issues.length) {
      this._triageSummary = null;
      this._lastTriageSignature = "";
      return;
    }
    this._triageInFlight = true;
    let shouldContinue = false;
    const progress = this._triageProgress || {
      total: this._issueTotal() || issues.length,
      processed: 0,
      reviewed: 0,
      remaining: this._issueTotal() || issues.length,
      batches: 0,
      insight: ""
    };
    progress.currentBatch = Math.min(AUTO_TRIAGE_BATCH_LIMIT, issues.length);
    this._triageProgress = progress;
    if (!options.background) {
      this._render();
    } else {
      this._renderAfterBackgroundUpdate();
    }
    try {
      const result = await this._call(
        "triage_issues",
        {
          limit: AUTO_TRIAGE_BATCH_LIMIT,
          skipIssueIds: Array.from(this._triageSeenIssueIds),
          force: options.force ? true : void 0
        },
        { quiet: true, recordResult: true, suppressError: true }
      );
      this._triageSummary = result || null;
      if (result?.ok === false) {
        this._triageProgress = {
          ...progress,
          insight: result.error || "Automatic review triage failed."
        };
        return;
      }
      const processed = Number(result?.processed) || 0;
      const reviewed = Number(result?.reviewed) || 0;
      const remaining = Number(result?.remaining);
      const processedIssueIds = Array.isArray(result?.processedIssueIds) ? result.processedIssueIds : [];
      processedIssueIds.forEach((id) => this._triageSeenIssueIds.add(String(id)));
      this._triageProgress = {
        ...progress,
        processed: Math.min(progress.total || processed, progress.processed + processed),
        reviewed: progress.reviewed + reviewed,
        remaining: Number.isFinite(remaining) ? remaining : progress.remaining,
        batches: progress.batches + 1,
        currentBatch: 0,
        insight: triageInsight(result)
      };
      if ((Number(result?.reviewed) || 0) > 0) {
        await this._call("issues", OPEN_ISSUES_PAYLOAD, { quiet: true });
        await this._call("browse", {}, { quiet: true });
        this._selectedReviewIds.clear();
        this._lastTriageSignature = itemsFromPayload(this._issues, ["issues"]).map((issue) => issueKey(issue)).sort().join("|");
      }
      shouldContinue = processed > 0 && (this._triageProgress.remaining || itemsFromPayload(this._issues, ["issues"]).length) > 0 && this._triageSeenIssueIds.size < (this._triageProgress.total || 0);
    } finally {
      this._triageInFlight = false;
      if (shouldContinue) {
        this._lastTriageSignature = "";
        this._queueAutoTriage({ force: true, background: true, continuation: true });
      }
      this._renderAfterBackgroundUpdate();
    }
  }
  _renderIngest() {
    return `
      <section class="grid two">
        <article class="panel">
          <h2>File</h2>
          <form data-form="upload">
            <label><span>File</span><input name="file" type="file"></label>
            ${this._advancedIngestFields({ privateHosts: true })}
            <button type="submit"><ha-icon icon="mdi:file-upload-outline"></ha-icon><span>Upload</span></button>
          </form>
        </article>
        <article class="panel">
          <h2>URL</h2>
          <form data-form="url">
            ${textInput("url", "URL", "url")}
            ${this._advancedIngestFields({ privateHosts: true })}
            <button type="submit"><ha-icon icon="mdi:link-plus"></ha-icon><span>Ingest URL</span></button>
          </form>
        </article>
        <article class="panel">
          <h2>Note</h2>
          <form data-form="note">
            <label><span>Body</span><textarea name="body" rows="7"></textarea></label>
            ${this._advancedIngestFields()}
            <button type="submit"><ha-icon icon="mdi:note-plus-outline"></ha-icon><span>Ingest Note</span></button>
          </form>
        </article>
        <article class="panel">
          <h2>Reference</h2>
          <form data-form="artifact">
            ${textInput("artifactId", "Artifact ID")}
            ${textInput("path", "Daemon Path")}
            ${textInput("uri", "URI")}
            ${this._advancedIngestFields({ privateHosts: true })}
            <button type="submit"><ha-icon icon="mdi:database-import-outline"></ha-icon><span>Ingest Reference</span></button>
          </form>
        </article>
      </section>
      ${this._resultPanel()}
    `;
  }
  _renderAsk() {
    const asking = this._busy === "ask";
    return `
      <section class="grid two">
        <article class="panel">
          <div class="panel-heading">
            <h2>Ask The House</h2>
            <div class="mini-actions">
              <button type="button" data-action="reindex" ${this._busy ? "disabled" : ""}><ha-icon icon="mdi:file-refresh-outline"></ha-icon><span>Reindex uploads</span></button>
            </div>
          </div>
          <form data-form="ask">
            <label><span>Question</span><textarea name="query" rows="6"></textarea></label>
            <details class="advanced">
              <summary>Advanced</summary>
              <div class="advanced-fields">
                ${textInput("limit", "Result Limit", "number")}
                ${textInput("mode", "Mode")}
                <label class="check"><input name="includeSources" type="checkbox" checked><span>Include sources</span></label>
                <label class="check"><input name="includeLinkedObjects" type="checkbox" checked><span>Include linked objects</span></label>
                <label class="check"><input name="includeConfidence" type="checkbox"><span>Include confidence</span></label>
              </div>
            </details>
            <button type="submit" ${asking ? "disabled" : ""}>
              <ha-icon class="${asking ? "spin" : ""}" icon="${asking ? "mdi:loading" : "mdi:message-processing-outline"}"></ha-icon>
              <span>${asking ? "Thinking" : "Ask"}</span>
            </button>
          </form>
        </article>
        <article class="panel">
          <h2>Answer</h2>
          ${this._answerText()}
        </article>
      </section>
      ${this._resultPanel()}
    `;
  }
  _renderLink() {
    return `
      <section class="grid two">
        <article class="panel">
          <h2>Link</h2>
          <form data-form="link">
            ${textInput("sourceId", "Source ID")}
            ${textInput("nodeId", "Node ID")}
            ${this._targetFields()}
            ${metadataField()}
            <button type="submit"><ha-icon icon="mdi:link-variant-plus"></ha-icon><span>Link</span></button>
          </form>
        </article>
        <article class="panel">
          <h2>Unlink</h2>
          <form data-form="unlink">
            ${textInput("sourceId", "Source ID")}
            ${textInput("nodeId", "Node ID")}
            ${this._targetFields()}
            ${metadataField()}
            <button type="submit"><ha-icon icon="mdi:link-variant-remove"></ha-icon><span>Unlink</span></button>
          </form>
        </article>
      </section>
      ${this._resultPanel()}
    `;
  }
  _renderRefinement() {
    const tasks = itemsFromPayload(this._refinement, ["tasks"]);
    const readiness = statusReadiness(this._status);
    const activeCount = tasks.filter((task) => ACTIVE_REFINEMENT_STATES.has(String(task?.state || ""))).length;
    const runSummary = refinementRunSummary(this._lastResult);
    return `
      <section class="grid two">
        <article class="panel">
          <div class="panel-heading">
            <h2>Readiness</h2>
            <div class="mini-actions">
              <button type="button" data-action="refinement_refresh"><ha-icon icon="mdi:refresh"></ha-icon><span>Refresh</span></button>
              <button type="button" data-action="refinement_run"><ha-icon icon="mdi:auto-fix"></ha-icon><span>Run refinement</span></button>
            </div>
          </div>
          <dl class="facts">
            <div><dt>State</dt><dd>${escapeHtml(readiness?.state || "unknown")}</dd></div>
            <div><dt>Open Issues</dt><dd>${escapeHtml(String(readiness?.openIssueCount ?? ""))}</dd></div>
            <div><dt>Active Tasks</dt><dd>${escapeHtml(String(readiness?.activeRefinementTaskCount ?? activeCount))}</dd></div>
            <div><dt>Needs Review</dt><dd>${escapeHtml(String(readiness?.needsReviewTaskCount ?? ""))}</dd></div>
            <div><dt>Task Records</dt><dd>${escapeHtml(String(tasks.length))}</dd></div>
          </dl>
        </article>
        <article class="panel">
          <h2>Task Filter</h2>
          <form data-form="refinement" class="inline-form">
            <label>
              <span>State</span>
              <select name="state">
                ${refinementStateOptions(this._refinementState)}
              </select>
            </label>
            <label>
              <span>Limit</span>
              <input name="limit" type="number" min="1" max="1000" value="${escapeAttr(String(this._refinementLimit))}">
            </label>
            <button type="submit"><ha-icon icon="mdi:filter-outline"></ha-icon><span>Apply</span></button>
          </form>
          <form data-form="refinement_run" class="refinement-run-form">
            <details class="advanced">
              <summary>Run targeted refinement</summary>
              <div class="advanced-fields">
                ${textInput("gapIds", "Gap IDs")}
                ${textInput("sourceIds", "Source IDs")}
                ${textInput("limit", "Limit", "number")}
                <label class="check"><input name="force" type="checkbox"><span>Force</span></label>
                <button type="submit"><ha-icon icon="mdi:auto-fix"></ha-icon><span>Run targeted refinement</span></button>
              </div>
            </details>
          </form>
        </article>
      </section>
      ${runSummary ? refinementRunPanel(runSummary) : ""}
      <section class="grid">
        <article class="panel">
          <h2>Refinement Tasks</h2>
          ${tasks.length ? `<div class="task-list" data-scroll-region="refinement-tasks">${tasks.map((task) => this._taskCard(task)).join("")}</div>` : `<p class="empty">No refinement tasks</p>`}
        </article>
      </section>
      ${this._resultPanel()}
    `;
  }
  _taskCard(task) {
    const id = task?.id || "";
    const state = task?.state || "unknown";
    const title = task?.subjectTitle || task?.title || task?.gapId || id || "Refinement task";
    const meta = [
      state,
      task?.priority,
      task?.trigger,
      task?.subjectKind,
      task?.blockedReason
    ].filter(Boolean).join(" - ");
    const canCancel = ACTIVE_REFINEMENT_STATES.has(String(state));
    return `
      <div class="task-card ${canCancel ? "active" : ""}">
        <ha-icon icon="${refinementTaskIcon(state)}"></ha-icon>
        <div>
          <strong>${escapeHtml(String(title))}</strong>
          <span>${escapeHtml(meta)}</span>
          <small>${escapeHtml(String(id))}</small>
          ${task?.gapId ? `<small>Gap ${escapeHtml(String(task.gapId))}</small>` : ""}
        </div>
        ${canCancel ? `<button type="button" data-action="refinement_cancel" data-task-id="${escapeAttr(String(id))}"><ha-icon icon="mdi:cancel"></ha-icon><span>Cancel</span></button>` : ""}
        <details>
          <summary>Trace and metadata</summary>
          <pre>${escapeHtml(JSON.stringify(task, null, 2))}</pre>
        </details>
      </div>
    `;
  }
  _renderReview() {
    const issues = this._visibleIssues();
    const selected = this._selectedIssues(issues);
    return `
      ${this._triageNotice()}
      <section class="grid two">
        ${this._reviewIssueList(issues, selected)}
        <article class="panel">
          <h2>Review</h2>
          ${selected.length ? this._reviewForm(selected) : `<p class="empty">No issue selected</p>`}
        </article>
      </section>
      ${this._resultPanel()}
    `;
  }
  _renderPages() {
    const pages = this._generatedPages();
    const selected = this._selectedPage(pages);
    const selectedKey = selected ? pageKey(selected) : "";
    const pageIndex = buildPageNavigationIndex(pages);
    return `
      <section class="page-workspace">
        <aside class="panel page-index">
          <div class="panel-heading">
            <h2>Pages</h2>
            <div class="mini-actions">
              <button type="button" data-action="sync"><ha-icon icon="mdi:sync"></ha-icon><span>Sync</span></button>
            </div>
          </div>
          ${pages.length ? `<div class="page-list" data-scroll-region="generated-pages">${pages.map((page) => this._pageCard(page, selectedKey)).join("")}</div>` : `<p class="empty">No generated pages yet</p>`}
        </aside>
        <article class="panel page-reader-panel">
          ${selected ? this._pageReader(selected, pages, pageIndex) : `<p class="empty">No page selected</p>`}
        </article>
      </section>
      <section class="grid two page-maintenance">
        <article class="panel">
          ${this._directPageTools()}
        </article>
        <article class="panel">
          ${this._dataPortabilityTools()}
        </article>
      </section>
      ${this._resultPanel()}
    `;
  }
  _selectedPage(pages) {
    if (!pages.length) {
      this._selectedPageKey = "";
      return null;
    }
    const selected = this._selectedPageKey ? pages.find((page2) => pageKey(page2) === this._selectedPageKey) : null;
    const page = selected || pages.find((item) => pageMarkdown(item)) || pages[0];
    this._selectedPageKey = pageKey(page);
    return page;
  }
  _generatedPages() {
    const pages = itemsFromPayload(this._pages, ["pages"]);
    if (pages.length) {
      return pages.sort(compareGeneratedPages);
    }
    const byId = /* @__PURE__ */ new Map();
    for (const source of [
      ...itemsFromPayload(this._sources, ["sources"]),
      ...itemsFromPayload(this._browse, ["sources"])
    ]) {
      if (!isGeneratedPageSource(source)) {
        continue;
      }
      const id = source?.id || source?.sourceId || JSON.stringify(source);
      byId.set(String(id), source);
    }
    return Array.from(byId.values()).sort(compareGeneratedPages);
  }
  _pageCard(page, selectedKey) {
    const source = pageSource(page);
    const metadata = pageMetadata(page);
    const title = pageTitle(page);
    const projection = pageProjection(page);
    const regeneration = metadata.regeneration || "automatic";
    const generatedAt = formatTimestamp(metadata.generatedAt || source?.updatedAt || source?.createdAt);
    const detail = [projectionLabel(projection), regeneration, generatedAt].filter(Boolean).join(" - ");
    const key = pageKey(page);
    const active = key && key === selectedKey;
    return `
      <button type="button" class="page-card ${active ? "selected" : ""}" data-action="page_select" data-page-key="${escapeAttr(key)}">
        <ha-icon icon="${pageIcon(projection)}"></ha-icon>
        <div>
          <strong>${escapeHtml(String(title))}</strong>
          <span>${escapeHtml(detail)}</span>
          ${source?.summary ? `<small>${escapeHtml(shortText(String(source.summary), 120))}</small>` : ""}
        </div>
      </button>
    `;
  }
  _pageReader(page, pages = [], pageIndex = buildPageNavigationIndex(pages)) {
    const source = pageSource(page);
    const metadata = pageMetadata(page);
    const title = pageTitle(page);
    const projection = pageProjection(page);
    const generatedAt = formatTimestamp(metadata.generatedAt || source?.updatedAt || source?.createdAt);
    const markdown = stripLeadingMarkdownTitle(pageMarkdown(page), title);
    const sourceUri = source?.sourceUri || source?.canonicalUri || "";
    const profile = pageProfile(page);
    const related = relatedPagesForPage(page, pages, pageIndex);
    const contextLinks = pageContextLinks(profile, pageIndex);
    const meta = [
      projectionLabel(projection),
      metadata.regeneration || "",
      generatedAt
    ].filter(Boolean);
    return `
      <div class="wiki-page">
        <header class="wiki-header">
          <div>
            <span class="wiki-kicker">${escapeHtml(projectionLabel(projection))}</span>
            <h1>${escapeHtml(String(title))}</h1>
          </div>
          ${meta.length ? `<div class="page-meta">${meta.map((item) => `<span>${escapeHtml(String(item))}</span>`).join("")}</div>` : ""}
          ${source?.summary ? `<p>${escapeHtml(String(source.summary))}</p>` : ""}
        </header>
        ${related.length ? linkedPagesPanel(related) : ""}
        ${contextLinks.length ? pageContextPanel(contextLinks) : ""}
        <div class="wiki-body">
          ${markdown ? renderMarkdown(markdown, { pageIndex, currentKey: pageKey(page) }) : `<p class="empty">This page has no rendered markdown yet.</p>`}
        </div>
        ${sourceUri || source?.id || page?.artifact?.id ? `<footer class="wiki-footer">
                ${sourceUri ? `<span>${escapeHtml(String(sourceUri))}</span>` : ""}
                ${source?.id ? `<span>Source ${escapeHtml(String(source.id))}</span>` : ""}
                ${page?.artifact?.id ? `<span>Artifact ${escapeHtml(String(page.artifact.id))}</span>` : ""}
              </footer>` : ""}
      </div>
    `;
  }
  _directPageTools() {
    return `
      <details class="advanced page-tools">
        <summary>Direct Refresh</summary>
        <form data-form="page">
          <label>
            <span>Type</span>
            <select name="pageType">
              <option value="room_page">Room page</option>
              <option value="device_passport">Device passport</option>
              <option value="packet">Packet</option>
            </select>
          </label>
          ${textInput("title", "Title")}
          ${textInput("areaId", "Area ID")}
          ${textInput("roomId", "Room ID")}
          ${textInput("deviceId", "Device ID")}
          ${textInput("packetKind", "Packet Kind")}
          ${textInput("sharingProfile", "Sharing Profile")}
          <button type="submit"><ha-icon icon="mdi:file-refresh-outline"></ha-icon><span>Refresh</span></button>
        </form>
      </details>
    `;
  }
  _dataPortabilityTools() {
    return `
      <details class="advanced page-tools">
        <summary>Export / Import</summary>
        <div class="advanced-fields">
          <form data-form="export">
            <button type="submit"><ha-icon icon="mdi:export"></ha-icon><span>Export Home Graph</span></button>
          </form>
          <form data-form="import">
            <label><span>Export JSON</span><textarea name="data" rows="7"></textarea></label>
            <button type="submit"><ha-icon icon="mdi:import"></ha-icon><span>Import Home Graph</span></button>
          </form>
          <form data-form="reset" class="danger-zone">
            <label class="check"><input name="dryRun" type="checkbox" checked><span>Preview only</span></label>
            <label><span>Reset confirmation</span><input name="confirm" type="text" autocomplete="off" placeholder="RESET"></label>
            <p>Preview first. Destructive reset requires typing RESET, clears this Home Graph space, then the panel syncs the real Home Assistant snapshot again.</p>
            <button type="submit"><ha-icon icon="mdi:database-refresh-outline"></ha-icon><span>Reset Home Graph</span></button>
          </form>
        </div>
      </details>
    `;
  }
  _advancedIngestFields(options = {}) {
    return `
      <details class="advanced">
        <summary>Advanced</summary>
        <div class="advanced-fields">
          ${textInput("title", "Title")}
          ${textInput("tags", "Tags")}
          ${options.privateHosts ? `<label class="check"><input name="allowPrivateHosts" type="checkbox"><span>Allow private hosts</span></label>` : ""}
          ${this._targetFields()}
          ${metadataField()}
        </div>
      </details>
    `;
  }
  _targetFields() {
    return `
      <div class="target-grid">
        <label>
          <span>Target Kind</span>
          <select name="targetKind">
            ${TARGET_KIND_OPTIONS.map((kind) => `<option value="${kind}">${kind}</option>`).join("")}
          </select>
        </label>
        ${textInput("targetId", "Target ID")}
        <label>
          <span>Relation</span>
          <select name="relation">
            ${RELATION_OPTIONS.map((relation) => `<option value="${relation}">${relation}</option>`).join("")}
          </select>
        </label>
      </div>
    `;
  }
  _listPanel(title, items) {
    return `
      <article class="panel">
        <h2>${escapeHtml(title)}</h2>
        ${items.length ? `<div class="list" data-scroll-region="${escapeAttr(`list:${title}`)}">${items.map((item) => this._listItem(item)).join("")}</div>` : `<p class="empty">No items</p>`}
      </article>
    `;
  }
  _reviewIssueList(issues, selected) {
    return `
      <article class="panel">
        <div class="panel-heading">
          <h2>Open Issues</h2>
          <div class="mini-actions">
            <button type="button" data-action="review_run_triage">Re-run triage</button>
            <button type="button" data-action="review_select_all">Select all visible</button>
            <button type="button" data-action="review_clear">Clear</button>
          </div>
        </div>
        ${issues.length ? `<div class="issue-list" data-scroll-region="review-issues">${issues.map((issue) => this._issueButton(issue, selected)).join("")}</div>` : `<p class="empty">No open issues</p>`}
      </article>
    `;
  }
  _triageNotice() {
    const progress = this._triageProgress;
    if (this._triageInFlight) {
      return this._triageProgressNotice("GoodVibes is classifying review issues.");
    }
    if (this._triageQueued) {
      return this._triageProgressNotice("GoodVibes is continuing review triage.");
    }
    if (!this._triageSummary) {
      return "";
    }
    const reviewed = Number(this._triageSummary.reviewed) || 0;
    const remaining = Number(this._triageSummary.remaining) || 0;
    const skipped = Number(this._triageSummary.skipped) || 0;
    if (this._triageSummary.ok === false) {
      return this._triageProgressNotice(
        `GoodVibes could not finish automatic review triage: ${this._triageSummary.error || "request failed"}`
      );
    }
    if (this._triageSummary.reason === "no-untriaged-open-issues" && skipped) {
      return `<div class="notice">${escapeHtml(
        `GoodVibes already classified the current review queue; ${remaining} issue(s) still need manual review.`
      )}</div>`;
    }
    if (!reviewed && !remaining) {
      return "";
    }
    if (progress) {
      return this._triageProgressNotice(
        reviewed ? `GoodVibes auto-reviewed ${reviewed} issue(s) in the last batch.` : "GoodVibes checked the last batch; those issues still need review."
      );
    }
    const message = reviewed ? `GoodVibes auto-reviewed ${reviewed} issue(s); ${remaining} still need review.` : `GoodVibes checked the review queue; ${remaining} issue(s) still need review.`;
    return `<div class="notice">${escapeHtml(message)}</div>`;
  }
  _triageProgressNotice(message) {
    const progress = this._triageProgress;
    if (!progress) {
      return `<div class="notice">${escapeHtml(message)}</div>`;
    }
    const total = Math.max(Number(progress.total) || 0, 1);
    const processed = Math.min(Number(progress.processed) || 0, total);
    const percent = Math.max(0, Math.min(100, Math.round(processed / total * 100)));
    const detail = [
      `${processed}/${total} checked`,
      `${Number(progress.reviewed) || 0} auto-reviewed`,
      `${Number(progress.remaining) || 0} still open`
    ].join(" - ");
    return `
      <div class="notice">
        <div>${escapeHtml(message)}</div>
        <div class="progress" aria-label="Review triage progress">
          <span style="width: ${percent}%"></span>
        </div>
        <small>${escapeHtml(detail)}</small>
        ${progress.insight ? `<small>${escapeHtml(progress.insight)}</small>` : ""}
      </div>
    `;
  }
  _issueTotal() {
    const candidates = [
      this._status?.issueCount,
      this._status?.status?.issueCount,
      this._issues?.issueCount,
      this._issues?.count,
      this._issues?.total,
      this._issues?.result?.issueCount,
      this._issues?.result?.count,
      this._issues?.result?.total
    ];
    for (const candidate of candidates) {
      const value = Number(candidate);
      if (Number.isFinite(value) && value >= 0) {
        return value;
      }
    }
    return itemsFromPayload(this._issues, ["issues"]).length;
  }
  _issueButton(issue, selected) {
    const key = issueKey(issue);
    const selectedKeys = new Set(selected.map((entry) => issueKey(entry)));
    const active = selectedKeys.has(key);
    const status = [issue.severity, issue.code, issue.status].filter(Boolean).join(" - ");
    return `
      <button type="button" class="issue-card ${active ? "selected" : ""}" data-select-issue="${escapeAttr(key)}">
        <ha-icon icon="${active ? "mdi:checkbox-marked-outline" : "mdi:checkbox-blank-outline"}"></ha-icon>
        <strong>${escapeHtml(issueTitle(issue))}</strong>
        <span>${escapeHtml(issueMessage(issue))}</span>
        ${status ? `<small>${escapeHtml(status)}</small>` : ""}
      </button>
    `;
  }
  _toggleReviewSelection(key) {
    if (!key) {
      return;
    }
    if (this._selectedReviewIds.has(key)) {
      this._selectedReviewIds.delete(key);
      return;
    }
    this._selectedReviewIds.add(key);
  }
  _visibleIssues() {
    return this._filtered(
      itemsFromPayload(this._issues, ["issues"]).filter((issue) => isOpenIssue(issue))
    );
  }
  _selectedIssues(issues) {
    const visibleKeys = new Set(issues.map((issue) => issueKey(issue)));
    for (const key of Array.from(this._selectedReviewIds)) {
      if (!visibleKeys.has(key)) {
        this._selectedReviewIds.delete(key);
      }
    }
    return issues.filter((issue) => this._selectedReviewIds.has(issueKey(issue)));
  }
  _reviewForm(issues) {
    const first = issues[0];
    const count = issues.length;
    const canResolveSource = issues.every((issue) => isSourceResolvableIssue(issue));
    return `
      <div class="selected-issue">
        <strong>${escapeHtml(count === 1 ? issueTitle(first) : `${count} issues selected`)}</strong>
        <span>${escapeHtml(count === 1 ? issueMessage(first) : "The selected action and note will be applied to every selected issue.")}</span>
      </div>
      ${canResolveSource ? this._sourceResolutionForms(issues) : ""}
      <form data-form="review">
        <h3>${escapeHtml(canResolveSource ? "Review without adding a source" : "Review issue")}</h3>
        <label>
          <span>Action</span>
          <select name="action">
            ${reviewActionOptions(first, this._reviewAction, count, canResolveSource)}
          </select>
        </label>
        <label><span>Note</span><textarea name="note" rows="4" placeholder="Optional context, correction, or reason">${escapeHtml(this._reviewNote)}</textarea></label>
        <button type="submit"><ha-icon icon="mdi:check-decagram-outline"></ha-icon><span>Apply Review</span></button>
      </form>
    `;
  }
  _sourceResolutionForms(issues) {
    const selected = Array.isArray(issues) ? issues : [issues];
    if (!selected.length || selected.some((issue) => !issue?.nodeId)) {
      return "";
    }
    const bulk = selected.length > 1;
    const hidden = bulk ? reviewBulkSourceHiddenFields() : reviewSourceHiddenFields(selected[0]);
    const sourceField = this._sourcePicker();
    const heading = bulk ? `Add the same manual or source to ${selected.length} selected issues` : "Add the missing manual or source";
    return `
      <section class="source-resolution">
        <h3>${escapeHtml(heading)}</h3>
        <form data-form="${bulk ? "review_bulk_upload_source" : "review_upload_source"}">
          ${hidden}
          <label><span>File</span><input name="file" type="file"></label>
          <button type="submit"><ha-icon icon="mdi:file-upload-outline"></ha-icon><span>${bulk ? "Upload and link to selected" : "Upload and link"}</span></button>
        </form>
        <form data-form="${bulk ? "review_bulk_url_source" : "review_url_source"}">
          ${hidden}
          <label><span>URL</span><input name="url" type="url" autocomplete="off"></label>
          <label class="check"><input name="allowPrivateHosts" type="checkbox"><span>Allow private hosts</span></label>
          <button type="submit"><ha-icon icon="mdi:link-plus"></ha-icon><span>${bulk ? "Add URL and link to selected" : "Add URL and link"}</span></button>
        </form>
        <form data-form="${bulk ? "review_bulk_existing_source" : "review_existing_source"}">
          ${hidden}
          ${sourceField}
          <button type="submit"><ha-icon icon="mdi:link-variant-plus"></ha-icon><span>${bulk ? "Link source to selected" : "Link source"}</span></button>
        </form>
      </section>
    `;
  }
  _sourcePicker() {
    const sources = itemsFromPayload(this._sources, ["sources"]).filter(
      (source) => source?.id || source?.sourceId
    );
    if (!sources.length) {
      return textInput("sourceId", "Existing Source ID");
    }
    return `
      <label>
        <span>Existing Source</span>
        <select name="sourceId">
          ${sources.map((source) => sourceOption(source)).join("")}
        </select>
      </label>
    `;
  }
  _reviewPayload(issue, fields) {
    const action = fields.action;
    const removeTarget = action === "forget" && (issue.nodeId || issue.sourceId);
    return this._compact({
      issueId: removeTarget ? void 0 : issue.id || issue.issueId,
      sourceId: issue.sourceId,
      nodeId: issue.nodeId,
      action,
      value: semanticReviewValue(issue, fields),
      reviewer: "homeassistant"
    });
  }
  async _applyReview(fields) {
    this._reviewAction = fields.action || this._reviewAction;
    this._reviewNote = fields.note || "";
    const issues = this._selectedIssues(this._visibleIssues());
    if (!issues.length) {
      this._showError(new Error("Select one or more issues first."));
      return;
    }
    this._busy = "review";
    this._error = "";
    this._render();
    const results = [];
    for (const issue of issues) {
      const result = await this._call("review", this._reviewPayload(issue, fields), {
        quiet: true
      });
      results.push({ issueId: issue.id || issue.issueId, result });
      if (this._error) {
        break;
      }
    }
    const error = this._error;
    this._lastResult = {
      ok: !error,
      reviewed: results.length,
      results
    };
    if (!error) {
      this._selectedReviewIds.clear();
      this._reviewNote = "";
      await this._refreshAll();
    }
    this._busy = "";
    this._error = error;
    this._render();
  }
  _listItem(item) {
    const title = item.title || item.name || item.id || item.kind || "Item";
    const subtitle = item.id || item.sourceId || item.nodeId || item.kind || "";
    return `
      <div class="row">
        <div>
          <strong>${escapeHtml(String(title))}</strong>
          <span>${escapeHtml(String(subtitle))}</span>
        </div>
        <pre>${escapeHtml(JSON.stringify(item, null, 2))}</pre>
      </div>
    `;
  }
  _filtered(items) {
    if (!this._filter) {
      return items;
    }
    const needle = this._filter.toLowerCase();
    return items.filter((item) => JSON.stringify(item).toLowerCase().includes(needle));
  }
  _answerText() {
    const answer = normalizeAnswerPayload(this._answer);
    const text = answer.text || "";
    const thinking = this._busy === "ask";
    if (!text) {
      return thinking ? `<div class="thinking"><ha-icon class="spin" icon="mdi:loading"></ha-icon><span>Thinking through the Home Graph...</span></div>` : `<p class="empty">No answer</p>`;
    }
    const confidence = formatConfidence(answer.confidence);
    const repairStatus = answer.refinement?.status || answer.refinement?.state || "";
    const meta = [
      answer.synthesized === true ? "Synthesized" : "",
      answer.mode ? `Mode: ${answer.mode}` : "",
      confidence ? `Confidence: ${confidence}` : "",
      repairStatus ? `Repair: ${repairStatus}` : "",
      Array.isArray(answer.refinementTaskIds) && answer.refinementTaskIds.length ? `${answer.refinementTaskIds.length} refinement task(s)` : ""
    ].filter(Boolean);
    const refinementTasks = Array.isArray(answer.refinementTaskIds) ? answer.refinementTaskIds.map((id) => ({ id, title: `Refinement task ${id}` })) : [];
    const refinementRecords = answer.refinement && typeof answer.refinement === "object" ? [{ ...answer.refinement, title: answer.refinement.title || "Answer refinement" }] : [];
    return `
      <div class="answer answer-card">
        ${thinking ? `<div class="thinking inline"><ha-icon class="spin" icon="mdi:loading"></ha-icon><span>Updating answer...</span></div>` : ""}
        ${meta.length ? `<div class="answer-meta">${meta.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
        <div class="answer-text">${escapeHtml(String(text))}</div>
        ${this._answerRecords("Repair Status", refinementRecords, "mdi:progress-wrench", { limit: 1 })}
        ${this._answerRecords("Gaps To Repair", answer.gaps, "mdi:alert-circle-outline", { limit: 6 })}
        ${this._answerRecords("Refinement Tasks", refinementTasks, "mdi:auto-fix", { limit: 6 })}
        ${this._answerRecords("Sources", answer.sources, "mdi:file-document-outline", { limit: 8, collapsed: true })}
        ${this._answerRecords("Linked Home Objects", answer.linkedObjects, "mdi:vector-link", { limit: 8, collapsed: true })}
        ${this._answerRecords("Evidence Facts", answer.facts, "mdi:check-decagram-outline", { limit: 8, collapsed: true })}
      </div>
    `;
  }
  _answerRecords(title, records, icon, options = {}) {
    if (!Array.isArray(records) || !records.length) {
      return "";
    }
    const limit = options.limit || 12;
    const hiddenCount = Math.max(0, records.length - limit);
    const body = `
      <div class="answer-list">
        ${records.slice(0, limit).map((record) => this._answerRecord(record)).join("")}
        ${hiddenCount ? `<p class="empty">${escapeHtml(String(hiddenCount))} more in raw result.</p>` : ""}
      </div>
    `;
    if (options.collapsed) {
      return `
        <details class="answer-section answer-collapse">
          <summary><ha-icon icon="${icon}"></ha-icon><span>${escapeHtml(title)} (${escapeHtml(String(records.length))})</span></summary>
          ${body}
        </details>
      `;
    }
    return `
      <section class="answer-section">
        <h3><ha-icon icon="${icon}"></ha-icon><span>${escapeHtml(title)} (${escapeHtml(String(records.length))})</span></h3>
        ${body}
      </section>
    `;
  }
  _answerRecord(record) {
    const title = answerRecordTitle(record);
    const subtitle = answerRecordSubtitle(record);
    const summary = answerRecordSummary(record);
    return `
      <details class="answer-record">
        <summary>
          <strong>${escapeHtml(title)}</strong>
          ${subtitle ? `<span>${escapeHtml(subtitle)}</span>` : ""}
        </summary>
        ${summary ? `<p>${escapeHtml(summary)}</p>` : ""}
        <pre>${escapeHtml(JSON.stringify(record, null, 2))}</pre>
      </details>
    `;
  }
  _markdownPreview() {
    const page = itemsFromPayload(this._pages, ["pages"]).find((item) => item?.markdown);
    if (page?.markdown) {
      return this._pageReader(page, this._generatedPages());
    }
    const result = this._lastResult.result || this._lastResult;
    return result?.markdown ? `<div class="wiki-page compact"><div class="wiki-body">${renderMarkdown(result.markdown)}</div></div>` : `<p class="empty">No generated content</p>`;
  }
  _resultPanel() {
    const summary = operationSummaryPanel(this._lastResult);
    return `
      ${summary}
      <details class="result">
        <summary>Last result</summary>
        <pre>${escapeHtml(JSON.stringify(this._lastResult || {}, null, 2))}</pre>
      </details>
    `;
  }
  _statusLine() {
    if (this._error) {
      return this._error;
    }
    const status = statusValue(this._status.status);
    const readiness = statusReadiness(this._status).state || "";
    const issueCount = itemsFromPayload(this._issues, ["issues"]).length;
    return [status, readiness, issueCount ? `${issueCount} issue(s)` : ""].filter(Boolean).join(" - ");
  }
  _styles() {
    return `
      :host {
        background: var(--primary-background-color);
        color: var(--primary-text-color);
        display: block;
        min-height: 100vh;
      }
      .shell {
        margin: 0 auto;
        max-width: 1280px;
        padding: 20px;
      }
      .topbar,
      .tabs,
      .actions,
      .identity {
        align-items: center;
        display: flex;
      }
      .topbar {
        gap: 16px;
        justify-content: space-between;
        margin-bottom: 16px;
      }
      .identity {
        gap: 12px;
        min-width: 0;
      }
      .logo {
        align-items: center;
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        display: inline-flex;
        height: 44px;
        justify-content: center;
        width: 44px;
      }
      .logo ha-icon {
        color: var(--primary-color);
      }
      h1,
      h2,
      p {
        margin: 0;
      }
      h1 {
        font-size: 24px;
        font-weight: 500;
      }
      h2 {
        font-size: 16px;
        font-weight: 500;
        margin-bottom: 12px;
      }
      h3 {
        font-size: 14px;
        font-weight: 500;
        margin: 0;
      }
      .identity p {
        color: var(--secondary-text-color);
        font-size: 13px;
        margin-top: 3px;
      }
      .actions,
      .tabs {
        gap: 8px;
      }
      button {
        align-items: center;
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        color: var(--primary-text-color);
        cursor: pointer;
        display: inline-flex;
        font: inherit;
        gap: 7px;
        min-height: 40px;
        padding: 0 12px;
      }
      button:hover,
      button.active {
        border-color: var(--primary-color);
        color: var(--primary-color);
      }
      button:disabled {
        cursor: wait;
        opacity: 0.65;
      }
      .tabs {
        border-bottom: 1px solid var(--divider-color);
        margin-bottom: 16px;
        overflow-x: auto;
        padding-bottom: 8px;
      }
      .grid {
        display: grid;
        gap: 16px;
        margin-bottom: 16px;
      }
      .grid.two {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .page-workspace {
        align-items: start;
        display: grid;
        gap: 16px;
        grid-template-columns: minmax(260px, 360px) minmax(0, 1fr);
        margin-bottom: 16px;
      }
      .panel {
        background: var(--card-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        padding: 16px;
      }
      .panel-heading {
        align-items: center;
        display: flex;
        gap: 12px;
        justify-content: space-between;
        margin-bottom: 12px;
      }
      .panel-heading h2 {
        margin-bottom: 0;
      }
      .mini-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
      .mini-actions button {
        min-height: 32px;
        padding: 6px 10px;
      }
      form {
        display: grid;
        gap: 12px;
      }
      .source-resolution {
        border-bottom: 1px solid var(--divider-color);
        display: grid;
        gap: 14px;
        margin-bottom: 14px;
        padding-bottom: 14px;
      }
      .source-resolution form {
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        padding: 12px;
      }
      .inline-form {
        align-items: end;
        grid-template-columns: minmax(180px, 1fr) minmax(120px, 220px) auto;
      }
      .map-form {
        align-items: end;
        display: grid;
        gap: 10px;
        grid-template-columns: minmax(180px, 280px) minmax(90px, 140px) auto auto auto auto;
      }
      .map-workspace {
        display: grid;
        gap: 12px;
        grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
      }
      .map-filters {
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        display: grid;
        gap: 12px;
        max-height: 680px;
        overflow: auto;
        padding: 12px;
      }
      .map-filter-heading {
        align-items: center;
        display: flex;
        justify-content: space-between;
      }
      .map-filter-heading span {
        color: var(--secondary-text-color);
        font-size: 12px;
      }
      .map-filter-heading button {
        min-height: 30px;
        padding: 5px 9px;
      }
      .facet-group {
        border-top: 1px solid var(--divider-color);
        display: grid;
        gap: 6px;
        padding-top: 8px;
      }
      .facet-group summary {
        align-items: center;
        cursor: pointer;
        display: flex;
        justify-content: space-between;
      }
      .facet-group summary span {
        color: var(--secondary-text-color);
        font-size: 12px;
        font-weight: 600;
      }
      .facet-group summary small {
        color: var(--secondary-text-color);
        font-size: 11px;
      }
      .facet-buttons {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        padding-top: 8px;
      }
      .facet-search {
        align-items: end;
        display: grid;
        gap: 8px;
        grid-template-columns: minmax(0, 1fr) auto auto;
      }
      .facet-search button {
        min-height: 40px;
      }
      .facet-note {
        color: var(--secondary-text-color);
        font-size: 12px;
        margin: 2px 0 0;
      }
      .selected-filters {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
      }
      .facet-chip {
        align-items: center;
        display: inline-flex;
        gap: 6px;
        min-height: 28px;
        padding: 4px 8px;
      }
      .facet-chip span {
        max-width: 220px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .facet-chip strong {
        color: var(--secondary-text-color);
        font-size: 11px;
        font-weight: 600;
      }
      .facet-chip.active {
        border-color: var(--accent-color);
        color: var(--accent-color);
      }
      .map-main {
        min-width: 0;
      }
      .map-canvas {
        background: var(--primary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        display: grid;
        min-height: 520px;
        overflow: auto;
      }
      .map-empty {
        align-content: center;
        color: var(--secondary-text-color);
        display: grid;
        gap: 8px;
        justify-items: center;
        min-height: 520px;
        padding: 24px;
        text-align: center;
      }
      .map-empty ha-icon {
        color: var(--secondary-text-color);
        --mdc-icon-size: 34px;
      }
      .map-empty strong {
        color: var(--primary-text-color);
      }
      .map-empty span {
        max-width: 520px;
      }
      .map-image {
        display: block;
        height: auto;
        min-width: 760px;
        width: 100%;
      }
      .map-stats {
        color: var(--secondary-text-color);
        display: flex;
        flex-wrap: wrap;
        font-size: 12px;
        gap: 10px;
        margin-top: 10px;
      }
      label {
        display: grid;
        gap: 5px;
      }
      label span,
      dt {
        color: var(--secondary-text-color);
        font-size: 12px;
      }
      input,
      select,
      textarea {
        background: var(--primary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        box-sizing: border-box;
        color: var(--primary-text-color);
        font: inherit;
        min-height: 40px;
        padding: 8px 10px;
        width: 100%;
      }
      textarea {
        resize: vertical;
      }
      .advanced {
        border-top: 1px solid var(--divider-color);
        padding-top: 8px;
      }
      .advanced summary {
        color: var(--secondary-text-color);
        cursor: pointer;
        font-size: 13px;
      }
      .advanced-fields {
        display: grid;
        gap: 12px;
        padding-top: 12px;
      }
      .danger-zone {
        border-top: 1px solid var(--error-color, #db4437);
        display: grid;
        gap: 10px;
        padding-top: 12px;
      }
      .danger-zone p {
        color: var(--secondary-text-color);
        font-size: 12px;
        margin: 0;
      }
      .check {
        align-items: center;
        display: flex;
        gap: 8px;
      }
      .check input {
        min-height: auto;
        width: auto;
      }
      .target-grid {
        display: grid;
        gap: 12px;
        grid-template-columns: minmax(120px, 1fr) minmax(160px, 1fr) minmax(120px, 1fr);
      }
      .facts {
        display: grid;
        gap: 10px;
        margin: 0;
      }
      .facts div {
        display: grid;
        gap: 4px;
      }
      dd {
        margin: 0;
        overflow-wrap: anywhere;
      }
      .list {
        display: grid;
        gap: 10px;
        max-height: 560px;
        overflow: auto;
      }
      .issue-list {
        display: grid;
        gap: 10px;
        max-height: 560px;
        overflow: auto;
      }
      .page-list {
        display: grid;
        gap: 10px;
        max-height: calc(100vh - 250px);
        overflow: auto;
      }
      .task-list {
        display: grid;
        gap: 10px;
        max-height: 660px;
        overflow: auto;
      }
      .task-card {
        align-items: start;
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        display: grid;
        gap: 10px;
        grid-template-columns: 28px minmax(0, 1fr) auto;
        padding: 12px;
      }
      .task-card.active {
        border-color: var(--primary-color);
      }
      .task-card ha-icon {
        color: var(--primary-color);
        margin-top: 1px;
      }
      .task-card strong,
      .task-card span,
      .task-card small {
        display: block;
        overflow-wrap: anywhere;
      }
      .task-card span,
      .task-card small {
        color: var(--secondary-text-color);
        font-size: 12px;
        margin-top: 3px;
      }
      .task-card details {
        grid-column: 1 / -1;
      }
      .task-card button {
        min-height: 32px;
        padding: 5px 9px;
      }
      .page-card {
        align-items: start;
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        display: grid;
        gap: 10px;
        grid-template-columns: 28px minmax(0, 1fr);
        justify-items: start;
        min-height: 0;
        padding: 12px;
        text-align: left;
        width: 100%;
      }
      .page-card.selected {
        border-color: var(--primary-color);
        color: var(--primary-color);
      }
      .page-card ha-icon {
        color: var(--primary-color);
        margin-top: 1px;
      }
      .page-card strong,
      .page-card span,
      .page-card small {
        display: block;
        overflow-wrap: anywhere;
      }
      .page-card span,
      .page-card small {
        color: var(--secondary-text-color);
        font-size: 12px;
        margin-top: 3px;
      }
      .page-reader-panel {
        min-height: calc(100vh - 210px);
        overflow: hidden;
      }
      .page-tools form {
        margin-top: 12px;
      }
      .wiki-page {
        display: grid;
        gap: 20px;
      }
      .wiki-header {
        border-bottom: 1px solid var(--divider-color);
        display: grid;
        gap: 10px;
        padding-bottom: 16px;
      }
      .wiki-header h1 {
        font-size: 30px;
        line-height: 1.15;
        margin: 0;
      }
      .wiki-kicker {
        color: var(--primary-color);
        display: block;
        font-size: 12px;
        font-weight: 600;
        margin-bottom: 6px;
        text-transform: uppercase;
      }
      .page-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
      .page-meta span {
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 999px;
        color: var(--secondary-text-color);
        font-size: 12px;
        padding: 4px 8px;
      }
      .wiki-header p {
        color: var(--secondary-text-color);
        line-height: 1.5;
      }
      .linked-pages {
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        display: grid;
        gap: 12px;
        padding: 12px;
      }
      .linked-pages h2 {
        font-size: 15px;
        margin: 0;
      }
      .linked-page-list {
        display: grid;
        gap: 8px;
        grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      }
      .linked-page {
        align-items: start;
        background: var(--card-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        display: grid;
        gap: 8px;
        grid-template-columns: 24px minmax(0, 1fr);
        justify-items: start;
        min-height: 48px;
        padding: 9px 10px;
        text-align: left;
      }
      .linked-page ha-icon {
        color: var(--primary-color);
        margin-top: 1px;
      }
      .linked-page strong,
      .linked-page small {
        display: block;
        overflow-wrap: anywhere;
      }
      .linked-page small {
        color: var(--secondary-text-color);
        font-size: 12px;
        margin-top: 2px;
      }
      .page-context {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
      .context-chip {
        align-items: center;
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 999px;
        display: inline-flex;
        gap: 6px;
        min-height: 30px;
        max-width: 100%;
        padding: 4px 9px;
      }
      .context-chip span {
        color: var(--secondary-text-color);
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
      }
      .context-chip strong {
        font-size: 12px;
        max-width: 260px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .wiki-body {
        color: var(--primary-text-color);
        display: block;
        font-size: 15px;
        line-height: 1.65;
        max-height: calc(100vh - 360px);
        overflow: auto;
        padding-right: 6px;
      }
      .wiki-body h1,
      .wiki-body h2,
      .wiki-body h3,
      .wiki-body h4 {
        color: var(--primary-text-color);
        font-weight: 600;
        line-height: 1.25;
        margin: 28px 0 10px;
      }
      .wiki-body h1:first-child,
      .wiki-body h2:first-child,
      .wiki-body h3:first-child {
        margin-top: 0;
      }
      .wiki-body h1 {
        font-size: 28px;
      }
      .wiki-body h2 {
        border-bottom: 1px solid var(--divider-color);
        font-size: 21px;
        padding-bottom: 6px;
      }
      .wiki-body h3 {
        font-size: 17px;
      }
      .wiki-body h4 {
        font-size: 15px;
      }
      .wiki-body p {
        margin: 0 0 12px;
      }
      .wiki-body ul,
      .wiki-body ol {
        margin: 0 0 16px 22px;
        padding: 0;
      }
      .wiki-body li {
        margin: 4px 0;
      }
      .wiki-body code {
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        font-family: var(--code-font-family, monospace);
        font-size: 0.92em;
        padding: 1px 4px;
      }
      .wiki-body pre {
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        overflow: auto;
        padding: 12px;
      }
      .wiki-body pre code {
        background: transparent;
        border: 0;
        padding: 0;
      }
      .wiki-body blockquote {
        border-left: 3px solid var(--primary-color);
        color: var(--secondary-text-color);
        margin: 0 0 16px;
        padding: 4px 0 4px 14px;
      }
      .wiki-body a {
        color: var(--primary-color);
      }
      .inline-page-link {
        background: transparent;
        border: 0;
        color: var(--primary-color);
        cursor: pointer;
        display: inline;
        font: inherit;
        min-height: 0;
        padding: 0;
        text-align: left;
        text-decoration: underline;
        text-underline-offset: 2px;
      }
      .inline-page-link:hover,
      .linked-page:hover,
      .context-chip:hover {
        border-color: var(--primary-color);
      }
      .list-separator {
        color: var(--secondary-text-color);
      }
      .wiki-footer {
        border-top: 1px solid var(--divider-color);
        color: var(--secondary-text-color);
        display: grid;
        font-size: 12px;
        gap: 4px;
        padding-top: 12px;
        overflow-wrap: anywhere;
      }
      .refinement-run-form {
        margin-top: 12px;
      }
      .issue-card {
        align-items: start;
        background: var(--secondary-background-color);
        border-color: var(--divider-color);
        color: var(--primary-text-color);
        display: grid;
        gap: 4px;
        grid-template-columns: 22px minmax(0, 1fr);
        justify-items: start;
        padding: 12px;
        text-align: left;
        width: 100%;
      }
      .issue-card:hover,
      .issue-card.selected {
        background: var(--primary-background-color);
        border-color: var(--primary-color);
      }
      .issue-card strong,
      .issue-card span,
      .issue-card small {
        overflow-wrap: anywhere;
      }
      .issue-card strong,
      .issue-card span,
      .issue-card small {
        grid-column: 2;
      }
      .issue-card ha-icon {
        grid-column: 1;
        grid-row: 1 / span 3;
        margin-top: -1px;
      }
      .issue-card span,
      .issue-card small {
        color: var(--secondary-text-color);
        font-size: 12px;
      }
      .selected-issue {
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        display: grid;
        gap: 4px;
        padding: 12px;
      }
      .selected-issue strong,
      .selected-issue span {
        overflow-wrap: anywhere;
      }
      .selected-issue span {
        color: var(--secondary-text-color);
        font-size: 12px;
      }
      .row {
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        padding: 10px;
      }
      .row strong,
      .row span {
        display: block;
        overflow-wrap: anywhere;
      }
      .row span {
        color: var(--secondary-text-color);
        font-size: 12px;
        margin-top: 2px;
      }
      pre {
        background: var(--secondary-background-color);
        border-radius: 8px;
        font-size: 12px;
        margin: 10px 0 0;
        max-height: 220px;
        overflow: auto;
        padding: 10px;
        white-space: pre-wrap;
      }
      .answer {
        line-height: 1.5;
        white-space: pre-wrap;
      }
      .answer-card {
        display: grid;
        gap: 14px;
      }
      .answer-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
      .answer-meta span {
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 999px;
        color: var(--secondary-text-color);
        font-size: 12px;
        padding: 3px 8px;
      }
      .answer-text {
        white-space: pre-wrap;
      }
      .answer-section {
        display: grid;
        gap: 8px;
      }
      .answer-collapse {
        border-top: 1px solid var(--divider-color);
        padding-top: 10px;
      }
      .answer-collapse summary {
        align-items: center;
        cursor: pointer;
        display: flex;
        font-size: 13px;
        gap: 6px;
      }
      .answer-section h3 {
        align-items: center;
        display: flex;
        font-size: 13px;
        gap: 6px;
        margin: 0;
      }
      .answer-list {
        display: grid;
        gap: 8px;
      }
      .answer-record {
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        padding: 10px;
      }
      .answer-record summary {
        cursor: pointer;
      }
      .answer-record strong,
      .answer-record span {
        display: block;
        overflow-wrap: anywhere;
      }
      .answer-record span {
        color: var(--secondary-text-color);
        font-size: 12px;
        margin-top: 2px;
      }
      .answer-record p {
        color: var(--secondary-text-color);
        margin-top: 8px;
      }
      .empty {
        color: var(--secondary-text-color);
      }
      .notice {
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        margin-bottom: 16px;
        padding: 10px 12px;
      }
      .notice.error {
        color: var(--error-color);
      }
      .notice small {
        color: var(--secondary-text-color);
        display: block;
        font-size: 12px;
        margin-top: 6px;
      }
      .working,
      .thinking {
        align-items: center;
        display: flex;
        gap: 10px;
      }
      .thinking {
        color: var(--secondary-text-color);
      }
      .thinking.inline {
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        padding: 10px;
      }
      .spin {
        animation: goodvibes-spin 900ms linear infinite;
      }
      @keyframes goodvibes-spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
      }
      .progress {
        background: var(--primary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 999px;
        height: 8px;
        margin-top: 8px;
        overflow: hidden;
      }
      .progress span {
        background: var(--primary-color);
        display: block;
        height: 100%;
        transition: width 180ms ease;
      }
      .result {
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        padding: 12px;
      }
      @media (max-width: 860px) {
        .topbar,
        .grid.two,
        .facet-search,
        .inline-form,
        .map-form,
        .map-workspace,
        .page-workspace,
        .target-grid {
          grid-template-columns: 1fr;
        }
        .topbar {
          align-items: stretch;
          display: grid;
        }
        .actions {
          flex-wrap: wrap;
        }
      }
    `;
  }
};
function textInput(name, label, type = "text") {
  return `<label><span>${label}</span><input name="${name}" type="${type}" autocomplete="off"></label>`;
}
function svgDataUrl(svg) {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(String(svg))}`;
}
function isGeneratedPageSource(source) {
  const metadata = source?.metadata && typeof source.metadata === "object" ? source.metadata : {};
  const tags = Array.isArray(source?.tags) ? source.tags.map((tag) => String(tag)) : [];
  return metadata.homeGraphGeneratedPage === true || metadata.homeGraphSourceKind === "generated-page" || Boolean(metadata.projectionKind) || tags.includes("generated-page");
}
function compareGeneratedPages(left, right) {
  const leftTime = generatedPageTime(left);
  const rightTime = generatedPageTime(right);
  if (leftTime !== rightTime) {
    return rightTime - leftTime;
  }
  const leftSource = left?.source || left;
  const rightSource = right?.source || right;
  return String(leftSource?.title || leftSource?.id || "").localeCompare(
    String(rightSource?.title || rightSource?.id || "")
  );
}
function generatedPageTime(page) {
  const source = page?.source || page;
  const metadata = source?.metadata && typeof source.metadata === "object" ? source.metadata : {};
  const value = metadata.generatedAt || source?.updatedAt || source?.createdAt || 0;
  const number = Number(value);
  if (Number.isFinite(number)) {
    return number;
  }
  const parsed = Date.parse(String(value));
  return Number.isFinite(parsed) ? parsed : 0;
}
function formatTimestamp(value) {
  const time = Number(value);
  if (Number.isFinite(time) && time > 0) {
    return new Date(time).toLocaleString();
  }
  if (value) {
    const parsed = Date.parse(String(value));
    if (Number.isFinite(parsed)) {
      return new Date(parsed).toLocaleString();
    }
  }
  return "";
}
function projectionLabel(value) {
  return String(value || "page").replace(/[_-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}
function pageIcon(value) {
  const kind = String(value || "").toLowerCase();
  if (kind.includes("device")) {
    return "mdi:card-account-details-outline";
  }
  if (kind.includes("room")) {
    return "mdi:floor-plan";
  }
  if (kind.includes("packet")) {
    return "mdi:file-document-multiple-outline";
  }
  return "mdi:file-document-outline";
}
function pageSource(page) {
  return page?.source && typeof page.source === "object" ? page.source : page || {};
}
function pageMetadata(page) {
  const source = pageSource(page);
  const sourceMetadata = source?.metadata && typeof source.metadata === "object" ? source.metadata : {};
  const artifactMetadata = page?.artifact?.metadata && typeof page.artifact.metadata === "object" ? page.artifact.metadata : {};
  return { ...artifactMetadata, ...sourceMetadata };
}
function pageKey(page) {
  const source = pageSource(page);
  return String(
    source?.id || source?.sourceId || page?.artifact?.id || source?.sourceUri || source?.canonicalUri || source?.title || page?.markdown || ""
  );
}
function pageTitle(page) {
  const source = pageSource(page);
  const markdownTitle = String(pageMarkdown(page)).match(/^#\s+(.+)$/m)?.[1];
  return String(
    markdownTitle || source?.title || source?.name || source?.sourceUri || source?.id || "Generated page"
  );
}
function pageProjection(page) {
  const source = pageSource(page);
  const metadata = pageMetadata(page);
  return metadata.projectionKind || metadata.kind || source?.sourceType || "page";
}
function pageMarkdown(page) {
  return String(
    page?.markdown || page?.content || page?.text || page?.artifact?.markdown || page?.artifact?.content || ""
  );
}
function buildPageNavigationIndex(pages) {
  const profiles = pages.map((page) => pageProfile(page)).filter((profile) => profile.key);
  const index = {
    profiles,
    byKey: /* @__PURE__ */ new Map(),
    bySourceId: /* @__PURE__ */ new Map(),
    byNodeId: /* @__PURE__ */ new Map(),
    byObjectId: /* @__PURE__ */ new Map(),
    byTitle: /* @__PURE__ */ new Map(),
    byAreaId: /* @__PURE__ */ new Map(),
    byDeviceId: /* @__PURE__ */ new Map()
  };
  profiles.forEach((profile) => {
    index.byKey.set(profile.key, profile);
    addIndexValue(index.bySourceId, profile.sourceId, profile);
    addIndexValue(index.byNodeId, profile.subject?.id, profile);
    addIndexValue(index.byNodeId, profile.target?.id, profile);
    addIndexValue(index.byObjectId, profile.subject?.objectId, profile);
    addIndexValue(index.byObjectId, profile.target?.objectId, profile);
    addIndexValue(index.byObjectId, profile.deviceId, profile);
    addIndexValue(index.byObjectId, profile.areaId, profile);
    pageLookupTitles(profile.page).forEach((title) => {
      const normalized = normalizePageLookup(title);
      if (normalized && !index.byTitle.has(normalized)) {
        index.byTitle.set(normalized, profile);
      }
    });
    if (profile.areaId && (!index.byAreaId.has(profile.areaId) || profile.projection === "room-page")) {
      index.byAreaId.set(profile.areaId, profile);
    }
    if (profile.deviceId && !index.byDeviceId.has(profile.deviceId)) {
      index.byDeviceId.set(profile.deviceId, profile);
    }
  });
  return index;
}
function addIndexValue(index, value, profile) {
  if (!value || index.has(String(value))) {
    return;
  }
  index.set(String(value), profile);
}
function pageProfile(page) {
  const metadata = pageMetadata(page);
  const source = pageSource(page);
  const markdown = pageMarkdown(page);
  const homeAssistant = metadata.homeAssistant && typeof metadata.homeAssistant === "object" ? metadata.homeAssistant : {};
  const title = pageTitle(page);
  const entityIds = uniqueStrings([
    ...extractEntityIds(markdown),
    ...normalizeLabelValues(homeAssistant.entityId),
    ...normalizeLabelValues(metadata.entityId)
  ]);
  const integrationDomains = uniqueStrings([
    ...extractIntegrationDomains(markdown),
    ...normalizeLabelValues(homeAssistant.integrationId),
    ...normalizeLabelValues(metadata.integrationId),
    ...normalizeLabelValues(metadata.integrationDomain)
  ]);
  const subject = objectRecord(page?.subject || metadata.subject || metadata.homeGraphSubject);
  const target = objectRecord(page?.target || metadata.target || metadata.homeGraphTarget);
  const neighbors = arrayField(page?.neighbors || metadata.neighbors).map(objectRecord).filter(Boolean);
  const relatedPages = arrayField(page?.relatedPages || metadata.relatedPages).filter(
    (item) => item && typeof item === "object"
  );
  return {
    page,
    key: pageKey(page),
    title,
    projection: pageProjection(page),
    sourceId: source?.id || source?.sourceId || "",
    subject,
    target,
    neighbors,
    relatedPages,
    areaId: subject?.areaId || metadata.areaId || homeAssistant.areaId || markdownField(markdown, "Area") || "",
    deviceId: (subject?.objectKind === "device" ? subject?.objectId : "") || (target?.objectKind === "device" ? target?.objectId : "") || metadata.deviceId || homeAssistant.deviceId || firstDeviceIdFromMarkdown(markdown) || "",
    manufacturer: metadata.manufacturer || markdownField(markdown, "Manufacturer") || "",
    model: metadata.model || markdownField(markdown, "Model") || "",
    entityIds,
    integrationDomains,
    markdown
  };
}
function objectRecord(value) {
  return value && typeof value === "object" ? value : null;
}
function pageLookupTitles(page) {
  const source = pageSource(page);
  return uniqueStrings([
    pageTitle(page),
    source?.title,
    source?.name,
    stripPageSuffix(source?.title),
    stripPageSuffix(pageTitle(page))
  ]);
}
function stripPageSuffix(value) {
  return String(value || "").replace(/\s+(passport|page|wiki)$/i, "").trim();
}
function normalizePageLookup(value) {
  return String(value || "").toLowerCase().replace(/\s+(passport|page|wiki)$/g, "").replace(/[\u2010-\u2015]/g, "-").replace(/[^a-z0-9]+/g, " ").trim();
}
function markdownField(markdown, label) {
  const pattern = new RegExp(`^[-*]\\s+${escapeRegExp(label)}:\\s*(.+)$`, "im");
  const match = String(markdown || "").match(pattern);
  return match ? match[1].trim() : "";
}
function firstDeviceIdFromMarkdown(markdown) {
  const match = String(markdown || "").match(/\bdevice\s+([a-f0-9]{16,})\b/i);
  return match ? match[1] : "";
}
function extractEntityIds(markdown) {
  const matches = String(markdown || "").match(/\b[a-z_]+\.[a-z0-9_]+\b/gi) || [];
  return matches;
}
function extractIntegrationDomains(markdown) {
  const matches = [];
  const text = String(markdown || "");
  let match;
  const pattern = /\bintegration\s+([a-z0-9_]+)/gi;
  while (match = pattern.exec(text)) {
    matches.push(match[1]);
  }
  return matches;
}
function relatedPagesForPage(page, pages, pageIndex) {
  const current = pageProfile(page);
  const related = /* @__PURE__ */ new Map();
  const add = (profile, reason, weight = 10) => {
    if (!profile?.key || profile.key === current.key) {
      return;
    }
    const existing = related.get(profile.key);
    if (!existing || weight < existing.weight) {
      related.set(profile.key, { profile, reason, weight });
    }
  };
  current.relatedPages.forEach((entry) => {
    const profile = pageProfileFromReference(entry, pageIndex);
    add(profile, entry.relation || entry.projectionKind || "Related page", 0);
  });
  current.neighbors.forEach((entry) => {
    const profile = pageProfileFromReference(entry, pageIndex);
    add(profile, entry.relation || "Graph neighbor", 4);
  });
  const isRoom = current.projection === "room-page" || Boolean(current.areaId && !current.deviceId);
  if (current.areaId) {
    const room = pageIndex.byAreaId.get(current.areaId);
    if (room && room.projection === "room-page") {
      add(room, "Room", 1);
    }
  }
  pageIndex.profiles.forEach((profile) => {
    const isDevice = profile.projection === "device-passport" || Boolean(profile.deviceId);
    if (isRoom && isDevice && profile.areaId === current.areaId) {
      add(profile, "Device in this room", 2);
      return;
    }
    if (current.deviceId && profile.markdown.includes(current.deviceId)) {
      add(profile, "Mentions this device", 3);
      return;
    }
    if (profile.deviceId && current.markdown.includes(profile.deviceId)) {
      add(profile, "Linked device", 3);
      return;
    }
    if (current.areaId && isDevice && profile.areaId === current.areaId) {
      add(profile, "Nearby device", 5);
      return;
    }
    if (profile.title && current.markdown.includes(profile.title)) {
      add(profile, "Mentioned page", 6);
    }
  });
  return Array.from(related.values()).sort((left, right) => left.weight - right.weight || left.profile.title.localeCompare(right.profile.title)).slice(0, 18);
}
function pageProfileFromReference(entry, pageIndex) {
  if (!entry || typeof entry !== "object") {
    return null;
  }
  return pageIndex.byKey.get(String(entry.pageKey || "")) || pageIndex.bySourceId.get(String(entry.sourceId || entry.id || "")) || pageIndex.byNodeId.get(String(entry.id || entry.nodeId || "")) || pageIndex.byObjectId.get(String(entry.objectId || "")) || pageIndex.byTitle.get(normalizePageLookup(entry.title || entry.name || "")) || null;
}
function linkedPagesPanel(related) {
  return `
    <nav class="linked-pages" aria-label="Linked pages">
      <h2>Linked Pages</h2>
      <div class="linked-page-list">
        ${related.map(({ profile, reason }) => `
          <button type="button" class="linked-page" data-action="page_select" data-page-key="${escapeAttr(profile.key)}">
            <ha-icon icon="${pageIcon(profile.projection)}"></ha-icon>
            <span>
              <strong>${escapeHtml(profile.title)}</strong>
              <small>${escapeHtml(reason)}</small>
            </span>
          </button>
        `).join("")}
      </div>
    </nav>
  `;
}
function pageContextLinks(profile, pageIndex) {
  const links = [];
  const add = (label, value, action, data = {}) => {
    if (!value) {
      return;
    }
    links.push({ label, value, action, data });
  };
  const room = profile.areaId ? pageIndex.byAreaId.get(profile.areaId) : null;
  if (room?.key && room.key !== profile.key) {
    add("Room", room.title, "page_select", { pageKey: room.key });
  } else if (profile.areaId) {
    add("Area", profile.areaId, "page_map_filter", { mapFilterKey: "areaIds", mapFilterValue: profile.areaId });
  }
  if (profile.deviceId) {
    add("Device", shortText(profile.deviceId, 18), "page_map_filter", { mapFilterKey: "deviceIds", mapFilterValue: profile.deviceId });
  }
  if (profile.subject?.title && profile.subject?.id) {
    add("Subject", profile.subject.title, "page_map_query", { mapQuery: profile.subject.title });
  }
  if (profile.target?.title && profile.target?.id) {
    add("Target", profile.target.title, "page_map_query", { mapQuery: profile.target.title });
  }
  if (profile.model) {
    add("Model", profile.model, "page_map_query", { mapQuery: profile.model });
  }
  profile.integrationDomains.slice(0, 4).forEach(
    (domain) => add("Integration", domain, "page_map_filter", { mapFilterKey: "integrationDomains", mapFilterValue: domain })
  );
  profile.entityIds.slice(0, 6).forEach(
    (entityId) => add("Entity", entityId, "page_map_filter", { mapFilterKey: "entityIds", mapFilterValue: entityId })
  );
  return links;
}
function pageContextPanel(links) {
  return `
    <div class="page-context">
      ${links.map((link) => contextLinkButton(link)).join("")}
    </div>
  `;
}
function contextLinkButton(link) {
  const attrs = Object.entries(link.data || {}).map(([key, value]) => `data-${kebabCase(key)}="${escapeAttr(String(value))}"`).join(" ");
  return `
    <button type="button" class="context-chip" data-action="${escapeAttr(link.action)}" ${attrs}>
      <span>${escapeHtml(link.label)}</span>
      <strong>${escapeHtml(String(link.value))}</strong>
    </button>
  `;
}
function pageLinkForListItem(value, context = {}) {
  const pageIndex = context.pageIndex;
  if (!pageIndex?.byTitle) {
    return null;
  }
  const raw = String(value || "").trim();
  const candidates = [
    raw.split(/\s+-\s+/)[0],
    raw.split(/\s+--\s+/)[0],
    raw.split(":")[0],
    raw
  ].map((item) => item.trim()).filter(Boolean);
  for (const candidate of candidates) {
    const profile = pageIndex.byTitle.get(normalizePageLookup(candidate));
    if (profile?.key && profile.key !== context.currentKey) {
      return { profile, text: candidate, rest: raw.slice(candidate.length) };
    }
  }
  return null;
}
function renderListItem(value, context = {}) {
  const link = pageLinkForListItem(value, context);
  if (!link) {
    return renderGraphListItem(value, context);
  }
  return `
    <button type="button" class="inline-page-link" data-action="page_select" data-page-key="${escapeAttr(link.profile.key)}">
      ${escapeHtml(link.text)}
    </button>${renderInlineMarkdown(link.rest, context)}
  `;
}
function renderGraphListItem(value, context = {}) {
  const raw = String(value || "").trim();
  const parts = raw.split(/\s+-\s+/).map((part) => part.trim()).filter(Boolean);
  if (parts.length < 2) {
    return renderInlineMarkdown(value, context);
  }
  return parts.map((part, index) => renderGraphListSegment(part, index)).join('<span class="list-separator"> - </span>');
}
function renderGraphListSegment(part, index) {
  const area = part.match(/^area\s+(.+)$/i);
  if (area) {
    return inlineActionButton("page_map_filter", `area ${area[1]}`, {
      mapFilterKey: "areaIds",
      mapFilterValue: area[1]
    });
  }
  const integration = part.match(/^integration\s+(.+)$/i);
  if (integration) {
    return inlineActionButton("page_map_filter", `integration ${integration[1]}`, {
      mapFilterKey: "integrationDomains",
      mapFilterValue: integration[1]
    });
  }
  const device = part.match(/^device\s+([a-f0-9]{16,})$/i);
  if (device) {
    return inlineActionButton("page_map_filter", `device ${shortText(device[1], 12)}`, {
      mapFilterKey: "deviceIds",
      mapFilterValue: device[1]
    });
  }
  if (index === 0 || looksLikeModelToken(part)) {
    return inlineActionButton("page_map_query", part, { mapQuery: part });
  }
  return renderInlineMarkdown(part);
}
function inlineActionButton(action, label, data = {}) {
  const attrs = Object.entries(data).map(([key, value]) => `data-${kebabCase(key)}="${escapeAttr(String(value))}"`).join(" ");
  return `<button type="button" class="inline-page-link" data-action="${escapeAttr(action)}" ${attrs}>${escapeHtml(label)}</button>`;
}
function looksLikeModelToken(value) {
  const text = String(value || "").trim();
  return text.length >= 4 && /[a-z]/i.test(text) && /[0-9_:-]/.test(text) && !/^https?:\/\//i.test(text);
}
function stripLeadingMarkdownTitle(markdown, title) {
  const text = String(markdown || "");
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const firstContentIndex = lines.findIndex((line) => line.trim());
  if (firstContentIndex < 0) {
    return text;
  }
  const heading = lines[firstContentIndex].trim().match(/^#\s+(.+)$/);
  if (!heading) {
    return text;
  }
  const headingText = heading[1].trim().toLowerCase();
  const titleText = String(title || "").trim().toLowerCase();
  if (!titleText || headingText === titleText || titleText.includes(headingText)) {
    lines.splice(firstContentIndex, 1);
    return lines.join("\n").trimStart();
  }
  return text;
}
function renderMarkdown(markdown, context = {}) {
  const lines = String(markdown || "").replace(/\r\n?/g, "\n").split("\n");
  const html = [];
  let paragraph = [];
  let listType = "";
  let listItems = [];
  let codeLines = [];
  let inCode = false;
  const flushParagraph = () => {
    if (!paragraph.length) {
      return;
    }
    html.push(`<p>${renderInlineMarkdown(paragraph.join(" "), context)}</p>`);
    paragraph = [];
  };
  const flushList = () => {
    if (!listItems.length) {
      return;
    }
    const tag = listType === "ol" ? "ol" : "ul";
    html.push(`<${tag}>${listItems.map((item) => `<li>${renderListItem(item, context)}</li>`).join("")}</${tag}>`);
    listItems = [];
    listType = "";
  };
  const flushCode = () => {
    if (!codeLines.length) {
      return;
    }
    html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
    codeLines = [];
  };
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("```")) {
      flushParagraph();
      flushList();
      if (inCode) {
        flushCode();
        inCode = false;
      } else {
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeLines.push(line);
      continue;
    }
    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = Math.min(4, heading[1].length);
      html.push(`<h${level}>${renderInlineMarkdown(heading[2], context)}</h${level}>`);
      continue;
    }
    const unordered = trimmed.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      flushParagraph();
      if (listType && listType !== "ul") {
        flushList();
      }
      listType = "ul";
      listItems.push(unordered[1]);
      continue;
    }
    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (ordered) {
      flushParagraph();
      if (listType && listType !== "ol") {
        flushList();
      }
      listType = "ol";
      listItems.push(ordered[1]);
      continue;
    }
    if (trimmed.startsWith(">")) {
      flushParagraph();
      flushList();
      html.push(`<blockquote>${renderInlineMarkdown(trimmed.replace(/^>\s?/, ""), context)}</blockquote>`);
      continue;
    }
    flushList();
    paragraph.push(trimmed);
  }
  flushParagraph();
  flushList();
  if (inCode || codeLines.length) {
    flushCode();
  }
  return html.join("");
}
function renderInlineMarkdown(value, _context = {}) {
  let html = escapeHtml(value);
  html = html.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
    (_match, label, url) => `<a href="${escapeAttr(url)}" target="_blank" rel="noreferrer">${label}</a>`
  );
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  return html;
}
function refinementTaskIcon(state) {
  const value = String(state || "").toLowerCase();
  if (ACTIVE_REFINEMENT_STATES.has(value)) {
    return "mdi:progress-wrench";
  }
  if (value === "closed" || value === "verified") {
    return "mdi:check-decagram-outline";
  }
  if (value === "blocked" || value === "failed") {
    return "mdi:alert-circle-outline";
  }
  if (value === "needs_review") {
    return "mdi:clipboard-edit-outline";
  }
  if (value === "cancelled") {
    return "mdi:cancel";
  }
  return "mdi:auto-fix";
}
function refinementStateOptions(selected) {
  const states = [
    "",
    "detected",
    "queued",
    "searching",
    "evaluating",
    "extracting",
    "applying",
    "verified",
    "closed",
    "blocked",
    "suppressed",
    "needs_review",
    "cancelled",
    "failed"
  ];
  return states.map((state) => {
    const label = state ? projectionLabel(state) : "Any state";
    return `<option value="${escapeAttr(state)}" ${state === selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
}
function metadataField() {
  return `<label><span>Metadata JSON</span><textarea name="metadata" rows="3"></textarea></label>`;
}
function reviewActionOption(value, label, selected) {
  return `<option value="${escapeAttr(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
}
function reviewActionOptions(issue, selected, count, canResolveSource = false) {
  if (canResolveSource) {
    return [
      reviewActionOption(
        "reject",
        count > 1 ? "No manual/source needed for selected" : "No manual/source needed",
        selected
      ),
      reviewActionOption(
        "resolve",
        count > 1 ? "Mark selected resolved without adding source" : "Mark resolved without adding source",
        selected
      ),
      reviewActionOption("edit", "Save note or correction", selected),
      reviewActionOption("forget", "Remove linked graph item", selected)
    ].join("");
  }
  if (count === 1 && isBatteryIssue(issue)) {
    return [
      reviewActionOption("reject", "Does not use batteries", selected),
      reviewActionOption("accept", "Needs a battery type", selected),
      reviewActionOption("resolve", "Mark resolved", selected),
      reviewActionOption("edit", "Save note or correction", selected),
      reviewActionOption("forget", "Remove linked graph item", selected)
    ].join("");
  }
  return [
    reviewActionOption("accept", "This issue is real", selected),
    reviewActionOption("reject", "Not applicable or incorrect", selected),
    reviewActionOption("resolve", "Fixed already", selected),
    reviewActionOption("edit", "Add note or correction", selected),
    reviewActionOption("forget", "Remove linked graph item", selected)
  ].join("");
}
function reviewSourceHiddenFields(issue) {
  return `
    <input type="hidden" name="issueId" value="${escapeAttr(issue?.id || issue?.issueId || "")}">
    <input type="hidden" name="targetKind" value="node">
    <input type="hidden" name="targetId" value="${escapeAttr(issue?.nodeId || "")}">
    <input type="hidden" name="relation" value="has_manual">
  `;
}
function reviewBulkSourceHiddenFields() {
  return '<input type="hidden" name="relation" value="has_manual">';
}
function sourceIdFromResult(fields, sourceResult) {
  const source = sourceResult?.source || sourceResult?.result?.source || sourceResult?.sources?.[0] || sourceResult?.result?.sources?.[0] || {};
  return String(
    fields?.sourceId || source?.id || source?.sourceId || sourceResult?.sourceId || sourceResult?.result?.sourceId || sourceResult?.id || ""
  );
}
function sourceLinkedReviewValue(sourceId, relation) {
  const value = {
    category: "source_linked",
    relation,
    reason: "Linked a manual/source to this Home Graph object."
  };
  if (sourceId) {
    value.sourceId = sourceId;
  }
  return value;
}
function triageInsight(result) {
  const processed = Number(result?.processed) || 0;
  const reviewed = Number(result?.reviewed) || 0;
  const skipped = Number(result?.skipped) || 0;
  const decisions = Array.isArray(result?.decisions) ? result.decisions : [];
  const kept = Math.max(0, processed - reviewed);
  const categories = /* @__PURE__ */ new Map();
  decisions.forEach((decision) => {
    const category = String(decision?.category || "").trim();
    if (!category) {
      return;
    }
    categories.set(category, (categories.get(category) || 0) + 1);
  });
  const topCategories = Array.from(categories.entries()).sort((left, right) => right[1] - left[1]).slice(0, 3).map(([category, count]) => `${category} (${count})`).join(", ");
  return [
    `Last batch: ${processed} checked, ${reviewed} auto-reviewed, ${kept} kept for review, ${skipped} already classified.`,
    topCategories ? `Top categories: ${topCategories}.` : ""
  ].filter(Boolean).join(" ");
}
function semanticReviewValue(issue, fields) {
  const action = fields.action || "";
  const note = fields.note || "";
  const code = String(issue?.code || "");
  const value = {};
  if (note) {
    value.note = note;
    value.reason = note;
  }
  if (action === "reject") {
    value.category = "not_applicable";
    if (code.endsWith("unknown_battery")) {
      value.fact = {
        ...value.fact || {},
        batteryPowered: false,
        batteryType: "none"
      };
      value.reason = value.reason || "This Home Graph object does not use batteries.";
    } else if (code.endsWith("missing_manual")) {
      value.fact = {
        ...value.fact || {},
        manualRequired: false
      };
      value.reason = value.reason || "This Home Graph object does not need a manual.";
    }
  }
  return Object.keys(value).length ? value : void 0;
}
function statusValue(status) {
  if (!status) {
    return "";
  }
  if (typeof status === "string") {
    return status;
  }
  if (status.status || status.state) {
    return status.status || status.state;
  }
  if (status.ok === true) {
    return "ok";
  }
  return JSON.stringify(status);
}
function statusCount(payload, key) {
  const value = payload?.[key] ?? payload?.status?.[key];
  return value === void 0 || value === null ? "" : String(value);
}
function statusCapabilities(payload) {
  const value = payload?.capabilities ?? payload?.status?.capabilities;
  return Array.isArray(value) ? value.join(", ") : "";
}
function statusReadiness(payload) {
  const value = payload?.readiness ?? payload?.status?.readiness;
  return value && typeof value === "object" ? value : {};
}
function readinessLabel(payload) {
  const readiness = statusReadiness(payload);
  const parts = [
    readiness.state || "unknown",
    readiness.openIssueCount !== void 0 ? `${readiness.openIssueCount} open issue(s)` : "",
    readiness.activeRefinementTaskCount !== void 0 ? `${readiness.activeRefinementTaskCount} active task(s)` : "",
    readiness.needsReviewTaskCount !== void 0 ? `${readiness.needsReviewTaskCount} needs review` : ""
  ].filter(Boolean);
  return parts.join(" - ");
}
function busyLabel(action) {
  const labels = {
    ask: "Thinking through the Home Graph",
    reindex: "Reindexing Home Graph sources",
    refinement_run: "Running Home Graph refinement",
    refinement_tasks: "Loading refinement tasks",
    map: "Updating the knowledge map",
    pages: "Loading automatic pages",
    upload: "Uploading and ingesting",
    sync: "Syncing Home Assistant context",
    review: "Applying review decisions"
  };
  return labels[action] || `Working: ${action}`;
}
function refinementStatusLabel(statusPayload, refinementPayload) {
  const readiness = statusReadiness(statusPayload);
  const tasks = itemsFromPayload(refinementPayload, ["tasks"]);
  const active = tasks.filter((task) => ACTIVE_REFINEMENT_STATES.has(String(task?.state || ""))).length;
  const needsReview = tasks.filter((task) => String(task?.state || "") === "needs_review").length;
  return [
    `${tasks.length} task record(s)`,
    `${readiness.activeRefinementTaskCount ?? active} active`,
    `${readiness.needsReviewTaskCount ?? needsReview} needs review`
  ].join(" - ");
}
function refinementRunSummary(payload) {
  const result = payload?.result && typeof payload.result === "object" ? payload.result : payload;
  if (!result || typeof result !== "object") {
    return null;
  }
  const keys = [
    "candidateGaps",
    "processedGaps",
    "requestedLimit",
    "effectiveLimit",
    "truncated",
    "budgetExhausted"
  ];
  return keys.some((key) => result[key] !== void 0) ? result : null;
}
function operationSummaryPanel(payload) {
  const result = payload?.result && typeof payload.result === "object" ? payload.result : payload;
  if (!result || typeof result !== "object" || result.ok === false) {
    return "";
  }
  const fields = operationSummaryFields(result);
  if (!fields.length) {
    return "";
  }
  return `
    <article class="panel operation-summary">
      <h2>${escapeHtml(operationSummaryTitle(result))}</h2>
      <dl class="facts">
        ${fields.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd></div>`).join("")}
      </dl>
    </article>
  `;
}
function operationSummaryTitle(result) {
  if (result.scanned !== void 0 || result.reparsed !== void 0) {
    return "Reindex Summary";
  }
  if (result.candidateGaps !== void 0 || result.processedGaps !== void 0) {
    return "Refinement Summary";
  }
  if (result.reviewed !== void 0) {
    return "Review Summary";
  }
  if (result.pages !== void 0) {
    return "Pages Summary";
  }
  return "Result Summary";
}
function operationSummaryFields(result) {
  const generated = result.generated && typeof result.generated === "object" ? result.generated : {};
  const semantic = result.semantic && typeof result.semantic === "object" ? result.semantic : {};
  const selfImprovement = semantic.selfImprovement && typeof semantic.selfImprovement === "object" ? semantic.selfImprovement : {};
  return [
    ["Scanned", result.scanned],
    ["Reparsed", result.reparsed],
    ["Skipped", result.skipped],
    ["Failed", result.failed],
    ["Changed Sources", result.changedSourceCount],
    ["Forced Sources", result.forcedSourceCount],
    ["Generated Pages Skipped", result.skippedGeneratedPageArtifactCount],
    ["Generated Pages Refreshed", result.refreshedGeneratedPageCount],
    ["Page Policy", result.generatedPagePolicyVersion],
    ["Coalesced", booleanLabel(result.coalesced)],
    ["Sources", Array.isArray(result.sources) ? result.sources.length : void 0],
    ["Failures", Array.isArray(result.failures) ? result.failures.length : void 0],
    ["Quality Issues", Array.isArray(result.qualityIssues) ? result.qualityIssues.length : void 0],
    ["Truncated", booleanLabel(result.truncated)],
    ["Budget Exhausted", booleanLabel(result.budgetExhausted)],
    ["Device Passports", generated.devicePassports],
    ["Room Pages", generated.roomPages],
    ["Page Artifacts", generated.artifacts],
    ["Page Sources", generated.sources],
    ["Semantic Scanned", semantic.scanned],
    ["Semantic Enriched", semantic.enriched],
    ["Semantic Skipped", semantic.skipped],
    ["Semantic Failed", semantic.failed],
    ["Candidate Gaps", result.candidateGaps ?? selfImprovement.candidateGaps],
    ["Processed Gaps", result.processedGaps ?? selfImprovement.processedGaps],
    ["Requested Limit", result.requestedLimit ?? selfImprovement.requestedLimit],
    ["Effective Limit", result.effectiveLimit ?? selfImprovement.effectiveLimit],
    ["Queued Tasks", result.queuedTasks ?? result.queuedTaskCount ?? selfImprovement.queuedTasks],
    ["Task IDs", Array.isArray(result.taskIds) ? result.taskIds.length : Array.isArray(selfImprovement.taskIds) ? selfImprovement.taskIds.length : void 0],
    ["Reviewed", result.reviewed]
  ].filter(([, value]) => value !== void 0 && value !== "");
}
function refinementRunPanel(result) {
  const fields = [
    ["Candidate Gaps", result.candidateGaps],
    ["Processed Gaps", result.processedGaps],
    ["Requested Limit", result.requestedLimit],
    ["Effective Limit", result.effectiveLimit],
    ["Truncated", booleanLabel(result.truncated)],
    ["Budget Exhausted", booleanLabel(result.budgetExhausted)],
    ["Queued Tasks", result.queuedTasks ?? result.queuedTaskCount],
    ["Task IDs", Array.isArray(result.taskIds) ? result.taskIds.length : void 0]
  ].filter(([, value]) => value !== void 0 && value !== "");
  if (!fields.length) {
    return "";
  }
  return `
    <section class="grid">
      <article class="panel">
        <h2>Latest Run</h2>
        <dl class="facts">
          ${fields.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd></div>`).join("")}
        </dl>
      </article>
    </section>
  `;
}
function booleanLabel(value) {
  return typeof value === "boolean" ? value ? "yes" : "no" : value;
}
function issueKey(issue) {
  return String(
    issue?.id || issue?.issueId || issue?.nodeId || issue?.sourceId || issue?.message || JSON.stringify(issue || {})
  );
}
function issueTitle(issue) {
  return String(
    issue?.title || issue?.message || issue?.code || issue?.id || issue?.issueId || "Home Graph issue"
  );
}
function issueMessage(issue) {
  const parts = [
    issue?.message && issue?.title ? issue.message : void 0,
    issue?.nodeId ? `Node ${issue.nodeId}` : void 0,
    issue?.sourceId ? `Source ${issue.sourceId}` : void 0
  ].filter(Boolean);
  return parts.length ? parts.join(" - ") : issue?.id || "";
}
function isOpenIssue(issue) {
  return String(issue?.status || "open").toLowerCase() === "open";
}
function isMissingSourceIssue(issue) {
  const text = [issue?.code, issue?.title, issue?.message].filter(Boolean).join(" ").toLowerCase();
  return text.includes("missing_manual") || text.includes("no linked manual") || text.includes("no linked source");
}
function isSourceResolvableIssue(issue) {
  return Boolean(issue?.nodeId) && isMissingSourceIssue(issue);
}
function isBatteryIssue(issue) {
  const text = [issue?.code, issue?.title, issue?.message].filter(Boolean).join(" ").toLowerCase();
  return text.includes("unknown_battery") || text.includes("battery type");
}
function sourceOption(source) {
  const id = source?.id || source?.sourceId || "";
  const title = source?.title || source?.name || source?.url || source?.uri || id || "Source";
  const label = id && title !== id ? `${title} (${id})` : title;
  return `<option value="${escapeAttr(id)}">${escapeHtml(String(label))}</option>`;
}
function itemsFromPayload(payload, keys) {
  if (!payload) {
    return [];
  }
  for (const key of keys) {
    if (Array.isArray(payload[key])) {
      return payload[key];
    }
  }
  if (Array.isArray(payload)) {
    return payload;
  }
  if (Array.isArray(payload.result)) {
    return payload.result;
  }
  if (payload.result && typeof payload.result === "object") {
    return itemsFromPayload(payload.result, keys);
  }
  return [];
}
function normalizeAnswerPayload(payload) {
  const result = payload?.result && typeof payload.result === "object" ? payload.result : payload || {};
  const answer = result?.answer && typeof result.answer === "object" ? result.answer : {};
  return {
    text: answer.text || result.text || "",
    mode: answer.mode ?? result.mode,
    confidence: answer.confidence ?? result.confidence,
    synthesized: answer.synthesized ?? result.synthesized,
    refinement: objectField(answer.refinement ?? result.refinement),
    refinementTaskIds: arrayField(answer.refinementTaskIds ?? result.refinementTaskIds),
    facts: arrayField(answer.facts ?? result.facts),
    gaps: arrayField(answer.gaps ?? result.gaps),
    sources: arrayField(answer.sources ?? result.sources),
    linkedObjects: arrayField(answer.linkedObjects ?? result.linkedObjects)
  };
}
function arrayField(value) {
  return Array.isArray(value) ? value : [];
}
function objectField(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}
function formatConfidence(value) {
  if (value === void 0 || value === null || value === "") {
    return "";
  }
  const number = Number(value);
  if (Number.isFinite(number)) {
    if (number <= 0) {
      return "";
    }
    return number <= 1 ? `${Math.round(number * 100)}%` : String(number);
  }
  return String(value);
}
function answerRecordTitle(record) {
  if (record === null || typeof record !== "object") {
    return shortText(String(record ?? "Record"), 140);
  }
  return shortText(
    String(
      record.title || record.name || record.summary || record.text || record.question || record.sourceUri || record.url || record.id || "Record"
    ),
    140
  );
}
function answerRecordSubtitle(record) {
  if (record === null || typeof record !== "object") {
    return "";
  }
  const metadata = record?.metadata && typeof record.metadata === "object" ? record.metadata : {};
  const confidence = formatConfidence(record.confidence);
  return [
    record.kind || record.sourceType || metadata.semanticKind,
    record.status,
    confidence ? `confidence ${confidence}` : "",
    record.sourceUri || record.url || record.canonicalUri
  ].filter(Boolean).map((item) => shortText(String(item), 140)).join(" - ");
}
function answerRecordSummary(record) {
  if (record === null || typeof record !== "object") {
    return "";
  }
  const text = record.summary || record.description || record.reason || record.evidence;
  return text ? shortText(String(text), 280) : "";
}
function shortText(value, limit) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, Math.max(0, limit - 1))}...` : text;
}
function isFormControl(element) {
  return Boolean(
    element && ["INPUT", "SELECT", "TEXTAREA"].includes(element.tagName)
  );
}
function isDirtyField(field) {
  if (!field?.name) {
    return false;
  }
  if (field.type === "file") {
    return Boolean(field.files?.length);
  }
  if (field.type === "checkbox" || field.type === "radio") {
    return field.checked !== field.defaultChecked;
  }
  if (field.tagName === "SELECT") {
    const defaultOption = Array.from(field.options).find(
      (option) => option.defaultSelected
    );
    const defaultValue = defaultOption?.value || field.options[0]?.value || "";
    return field.value !== defaultValue;
  }
  return field.value !== field.defaultValue;
}
function facetItems(values, key, labelIndex) {
  if (!values) {
    return [];
  }
  if (Array.isArray(values)) {
    return values.map((item) => {
      if (item && typeof item === "object") {
        const value2 = String(item.value ?? item.id ?? item.key ?? "");
        return {
          value: value2,
          label: facetItemLabel(item, value2),
          count: Number(item.count) || 0
        };
      }
      const value = String(item ?? "");
      return { value, label: friendlyFacetLabel(value), count: 0 };
    }).filter((item) => item.value).map((item) => enrichFacetItem(item, key, labelIndex));
  }
  if (typeof values === "object") {
    return Object.entries(values).map(([value, count]) => ({
      value,
      label: friendlyFacetLabel(value),
      count: Number(count) || 0
    })).filter((item) => item.value).map((item) => enrichFacetItem(item, key, labelIndex)).sort((left, right) => right.count - left.count || left.value.localeCompare(right.value));
  }
  return [];
}
function facetItemLabel(item, value) {
  const metadata = item.metadata && typeof item.metadata === "object" ? item.metadata : {};
  const ha = metadata.homeAssistant && typeof metadata.homeAssistant === "object" ? metadata.homeAssistant : {};
  return String(
    item.label || item.title || item.name || item.displayName || item.friendlyName || ha.name || ha.friendlyName || friendlyFacetLabel(value)
  );
}
function enrichFacetItem(item, key, labelIndex) {
  const value = String(item?.value || "");
  const indexed = labelIndex?.[key]?.get(value);
  const candidateLabel = indexed || item.label || "";
  const hasHumanLabel = isHumanFacetLabel(value, candidateLabel);
  const label = hasHumanLabel && candidateLabel !== value ? String(candidateLabel) : friendlyFacetLabel(value);
  return {
    ...item,
    label,
    hasHumanLabel
  };
}
function shouldShowFacetItem(key, item, group = {}) {
  if (group.noisy && looksLikeNoisyFacetLabel(item?.label || item?.value)) {
    return false;
  }
  if (!MAP_TECHNICAL_FILTERS.has(key) && !group.technical) {
    return Boolean(item?.value);
  }
  return Boolean(item?.hasHumanLabel);
}
function displayFacetValue(key, value, labelIndex) {
  const indexed = labelIndex?.[key]?.get(String(value || ""));
  return indexed || friendlyFacetLabel(value);
}
function selectedMapFilterLabel(key, value) {
  if (key === "entityIds" && String(value || "").startsWith("automation.")) {
    return "Automations";
  }
  return new Map(MAP_HA_FILTERS).get(key) || key;
}
function facetSearchText(item, key) {
  return [
    key,
    item?.value,
    item?.label,
    friendlyFacetLabel(item?.value)
  ].filter(Boolean).join(" ").toLowerCase();
}
function mapLabelIndex(map) {
  const index = {
    entityIds: /* @__PURE__ */ new Map(),
    deviceIds: /* @__PURE__ */ new Map(),
    integrationIds: /* @__PURE__ */ new Map(),
    areaIds: /* @__PURE__ */ new Map(),
    labels: /* @__PURE__ */ new Map()
  };
  const nodes = itemsFromPayload(map || {}, ["nodes"]);
  const edges = itemsFromPayload(map || {}, ["edges"]);
  const nodeTitles = /* @__PURE__ */ new Map();
  nodes.forEach((node) => {
    const title = humanMapTitle(node);
    const id = String(node?.id || "");
    if (id && title) {
      nodeTitles.set(id, title);
    }
    addIndexedLabels(index.entityIds, title, mapRecordValues(node, [
      "entityId",
      "entity_id",
      "entity",
      "uniqueId",
      "unique_id"
    ]));
    addIndexedLabels(index.deviceIds, title, mapRecordValues(node, [
      "deviceId",
      "device_id",
      "device"
    ]));
    addIndexedLabels(index.integrationIds, title, mapRecordValues(node, [
      "integrationId",
      "integration_id",
      "configEntryId",
      "config_entry_id"
    ]));
    addIndexedLabels(index.areaIds, title, mapRecordValues(node, [
      "areaId",
      "area_id",
      "area"
    ]));
    addIndexedLabels(index.labels, title, mapRecordValues(node, ["label", "labels"]));
  });
  edges.forEach((edge) => {
    if (edge?.source && edge?.sourceTitle) {
      nodeTitles.set(String(edge.source), String(edge.sourceTitle));
    }
    if (edge?.target && edge?.targetTitle) {
      nodeTitles.set(String(edge.target), String(edge.targetTitle));
    }
  });
  nodeTitles.forEach((title, id) => {
    if (!isRawTechnicalId(id)) {
      return;
    }
    addIndexedLabels(index.deviceIds, title, [id]);
    addIndexedLabels(index.entityIds, title, [id]);
    addIndexedLabels(index.integrationIds, title, [id]);
  });
  return index;
}
function mapRecordValues(record, keys) {
  const metadata = record?.metadata && typeof record.metadata === "object" ? record.metadata : {};
  const ha = metadata.homeAssistant && typeof metadata.homeAssistant === "object" ? metadata.homeAssistant : {};
  const containers = [record, record?.homeAssistant, record?.ha, metadata, ha].filter(
    (item) => item && typeof item === "object"
  );
  return keys.flatMap(
    (key) => containers.flatMap((item) => normalizeLabelValues(item?.[key]))
  );
}
function normalizeLabelValues(value) {
  if (Array.isArray(value)) {
    return value.flatMap((item) => normalizeLabelValues(item));
  }
  if (value && typeof value === "object") {
    return normalizeLabelValues(value.id || value.value || value.name);
  }
  return value === void 0 || value === null || value === "" ? [] : [String(value)];
}
function addIndexedLabels(index, title, values) {
  if (!title) {
    return;
  }
  values.forEach((value) => {
    if (!value || index.has(value)) {
      return;
    }
    index.set(value, title);
  });
}
function humanMapTitle(record) {
  const title = String(
    record?.title || record?.name || record?.label || record?.friendlyName || record?.displayName || ""
  ).trim();
  if (!title || isRawTechnicalId(title)) {
    return "";
  }
  return title;
}
function friendlyFacetLabel(value) {
  const text = String(value || "");
  if (/^[a-f0-9]{16,}$/i.test(text) || /^[a-f0-9]{8,}_.+/i.test(text)) {
    return `${text.slice(0, 8)}...`;
  }
  const entity = text.match(/^([a-z0-9_]+)\.(.+)$/);
  if (entity) {
    return `${entity[1].replace(/_/g, " ")}: ${entity[2].replace(/_/g, " ")}`;
  }
  return text.replace(/_/g, " ");
}
function isHumanFacetLabel(value, label) {
  const text = String(label || "").trim();
  if (!text) {
    return false;
  }
  const rawValue = String(value || "").trim();
  if (text === rawValue || text === friendlyFacetLabel(rawValue) || isRawTechnicalId(text)) {
    return !isRawTechnicalId(rawValue);
  }
  return !looksLikeRawIdToken(text);
}
function isRawTechnicalId(value) {
  const text = String(value || "");
  return looksLikeRawIdToken(text);
}
function looksLikeRawIdToken(value) {
  const text = String(value || "").trim();
  return /^[a-f0-9]{16,}$/i.test(text) || /^[a-f0-9]{8,}_.+/i.test(text) || /^[a-f0-9]{8,}[-_][a-f0-9_-]{8,}$/i.test(text);
}
function looksLikeNoisyFacetLabel(value) {
  const text = String(value || "").trim();
  if (!text) {
    return false;
  }
  const wordCount = text.split(/\s+/).filter(Boolean).length;
  return wordCount > 7 || /[?!.]$/.test(text) || /^(do not|never|always|make sure|check if|connect to|you have|everything you|can bluetooth|manuals?|missing[- ]|knowledge\.)/i.test(text);
}
function uniqueStrings(values) {
  return Array.from(
    new Set(
      values.map((value) => String(value || "").trim()).filter(Boolean)
    )
  );
}
function kebabCase(value) {
  return String(value || "").replace(/([a-z0-9])([A-Z])/g, "$1-$2").replace(/[_\s]+/g, "-").toLowerCase();
}
function escapeRegExp(value) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function escapeHtml(value) {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
function escapeAttr(value) {
  return escapeHtml(value);
}
customElements.define("goodvibes-home-panel", GoodVibesHomePanel);
