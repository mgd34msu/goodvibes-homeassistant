const DEFAULT_WS_TYPE = "goodvibes/home_graph/call";
const DEFAULT_UPLOAD_URL = "/api/goodvibes/home-graph/upload";
const AUTO_TRIAGE_BATCH_LIMIT = 25;
const OPEN_ISSUES_PAYLOAD = { status: "open" };
const ACTIVE_REFINEMENT_STATES = new Set([
  "queued",
  "searching",
  "evaluating",
  "extracting",
  "applying",
  "verifying",
]);

const TARGET_KIND_OPTIONS = [
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
  "node",
];

const RELATION_OPTIONS = [
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
  "mentioned_by",
];

const MAP_HA_FILTERS = [
  ["objectKinds", "Objects"],
  ["areaIds", "Areas"],
  ["integrationDomains", "Integrations"],
  ["domains", "Domains"],
  ["deviceClasses", "Classes"],
  ["labels", "Labels"],
  ["entityIds", "Entities"],
  ["deviceIds", "Devices"],
  ["integrationIds", "Integration IDs"],
];

class GoodVibesHomePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "browse";
    this._busy = "";
    this._error = "";
    this._status = {};
    this._sources = {};
    this._pages = {};
    this._refinement = {};
    this._refinementState = "";
    this._refinementLimit = 100;
    this._browse = {};
    this._map = {};
    this._issues = {};
    this._answer = {};
    this._lastResult = {};
    this._filter = "";
    this._mapLimit = 500;
    this._mapQuery = "";
    this._mapIncludeSources = true;
    this._mapIncludeIssues = false;
    this._mapIncludeGenerated = true;
    this._mapFilters = {};
    this._loaded = false;
    this._pendingBackgroundRender = false;
    this._selectedReviewIds = new Set();
    this._reviewAction = "reject";
    this._reviewNote = "";
    this._lastTriageSignature = "";
    this._triageInFlight = false;
    this._triageQueued = false;
    this._triageSummary = null;
    this._triageProgress = null;
    this._triageSeenIssueIds = new Set();
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
      this._call("refinement_tasks", { limit: this._refinementLimit }, { quiet: true }),
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
        config_entry_id: this._configEntryId || undefined,
        payload,
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
      credentials: "same-origin",
    };
    const token = this._hass?.auth?.data?.access_token;
    if (token && !this._hass?.fetchWithAuth) {
      options.headers = { Authorization: `Bearer ${token}` };
    }
    const response = this._hass?.fetchWithAuth
      ? await this._hass.fetchWithAuth(this._uploadUrl, options)
      : await fetch(this._uploadUrl, options);
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
          this._call("pages", { limit: 250, includeMarkdown: true }).catch((err) =>
            this._showError(err)
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
        includeLinkedObjects: fields.includeLinkedObjects,
      }));
      return;
    }
    if (name === "browse") {
      this._filter = fields.query || "";
      await this._call("browse", { limit: fields.limit || 250 });
      return;
    }
    if (name === "map") {
      this._mapLimit = Number(fields.limit) || 500;
      this._mapQuery = fields.query || "";
      this._mapIncludeSources = Boolean(fields.includeSources);
      this._mapIncludeIssues = Boolean(fields.includeIssues);
      this._mapIncludeGenerated = Boolean(fields.includeGenerated);
      await this._call("map", this._mapPayload());
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
          sourceIds: this._tagsFromText(fields.sourceIds),
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
          body: fields.body,
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
          uri: fields.uri,
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
        metadata: this._jsonFromText(fields.metadata),
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
        sourceId: fields.sourceId,
      });
      return;
    }
    if (name === "link" || name === "unlink") {
      await this._call(name, {
        sourceId: fields.sourceId,
        nodeId: fields.nodeId,
        target: this._targetFromFields(fields),
        metadata: this._jsonFromText(fields.metadata),
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
        sharingProfile: fields.sharingProfile,
      });
      return;
    }
    if (name === "export") {
      await this._call("export");
      return;
    }
    if (name === "import") {
      await this._call("import", {
        data: this._jsonFromText(fields.data),
      });
    }
  }

  _ingestPayload(fields, extra) {
    return this._compact({
      ...extra,
      title: fields.title,
      tags: this._tagsFromText(fields.tags),
      target: this._targetFromFields(fields),
      metadata: this._jsonFromText(fields.metadata),
      allowPrivateHosts: fields.allowPrivateHosts ? true : undefined,
    });
  }

  _reviewSourcePayload(fields, extra) {
    return this._ingestPayload(
      {
        ...fields,
        relation: fields.relation || "has_manual",
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
        reviewer: "homeassistant",
      }),
      { quiet: true }
    );
    const error = this._error;
    this._lastResult = {
      ok: !error,
      linkedSource: sourceResult,
      review,
    };
    if (!error) {
      this._selectedReviewIds.clear();
      await this._syncAndRefresh();
    } else {
      this._render();
    }
  }

  async _resolveBulkReviewIssuesWithSource(fields, sourceResult) {
    const issues = this._selectedIssues(this._visibleIssues()).filter((issue) =>
      isSourceResolvableIssue(issue)
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
            relation,
          },
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
          reviewer: "homeassistant",
        }),
        { quiet: true }
      );
      results.push({
        issueId: issue.id || issue.issueId,
        nodeId: issue.nodeId,
        link,
        review,
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
      source: sourceResult,
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
      return undefined;
    }
    const target = {
      kind: fields.targetKind,
      id: fields.targetId,
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
    if (value === undefined || value === null || value === "") {
      return;
    }
    formData.append(key, typeof value === "string" ? value : JSON.stringify(value));
  }

  _jsonFromText(value) {
    if (!value) {
      return undefined;
    }
    return JSON.parse(value);
  }

  _jsonOrText(value) {
    if (!value) {
      return undefined;
    }
    try {
      return JSON.parse(value);
    } catch (_err) {
      return value;
    }
  }

  _tagsFromText(value) {
    if (!value) {
      return undefined;
    }
    return value
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
  }

  _compact(value) {
    return Object.fromEntries(
      Object.entries(value).filter(([, item]) => {
        if (item === undefined || item === null || item === "") {
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
      Object.entries(this._mapFilters || {})
        .map(([key, values]) => [key, Array.from(values || []).filter(Boolean)])
        .filter(([, values]) => values.length)
    );
    return this._compact({
      limit: this._mapLimit,
      query: this._mapQuery,
      includeSources: this._mapIncludeSources,
      includeIssues: this._mapIncludeIssues,
      includeGenerated: this._mapIncludeGenerated,
      ha: Object.keys(ha).length ? ha : undefined,
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
    return Array.from(root.querySelectorAll("input, select, textarea")).some((field) =>
      isDirtyField(field)
    );
  }

  _captureScrollState() {
    const state = new Map();
    this.shadowRoot?.querySelectorAll("[data-scroll-region]").forEach((element) => {
      state.set(element.dataset.scrollRegion, {
        left: element.scrollLeft,
        top: element.scrollTop,
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
        ${
          this._tab !== "review" && (this._triageInFlight || this._triageQueued)
            ? this._triageProgressNotice("GoodVibes is classifying review issues.")
            : ""
        }
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
          <div class="map-filters">
            <div class="map-filter-heading">
              <span>${escapeHtml(String(selectedFilters))} selected</span>
              <button type="button" data-action="map_clear_filters">Clear filters</button>
            </div>
            ${this._selectedMapFilters()}
            ${this._mapFacetGroups(facets)}
          </div>
          <div class="map-canvas">
            ${this._mapVisual(map, nodes)}
          </div>
          <div class="map-stats">
            <span>${escapeHtml(String(map.nodeCount ?? nodes.length))} nodes</span>
            <span>${escapeHtml(String(map.edgeCount ?? edges.length))} edges</span>
            ${
              map.totalNodeCount !== undefined
                ? `<span>${escapeHtml(String(map.totalNodeCount))} matching records</span>`
                : ""
            }
            ${map.spaceId ? `<span>${escapeHtml(map.spaceId)}</span>` : ""}
          </div>
        </article>
      </section>
      ${this._resultPanel()}
    `;
  }

  _mapFacetGroups(facets) {
    const groups = MAP_HA_FILTERS
      .map(([key, label]) => this._mapFacetGroup(key, label, facets?.[key]))
      .filter(Boolean);
    return groups.length ? groups.join("") : `<p class="empty">No map filters available</p>`;
  }

  _mapFacetGroup(key, label, values) {
    const selected = this._mapFilters?.[key] || [];
    const baseItems = facetItems(values);
    const known = new Set(baseItems.map((item) => item.value));
    const selectedItems = selected
      .filter((value) => !known.has(value))
      .map((value) => ({ value, label: value, count: 0 }));
    const selectedKnownItems = baseItems.filter((item) => selected.includes(item.value));
    const selectedValues = new Set(
      [...selectedItems, ...selectedKnownItems].map((item) => item.value)
    );
    const topItems = baseItems.filter((item) => !selectedValues.has(item.value)).slice(0, 10);
    const items = [...selectedItems, ...selectedKnownItems, ...topItems];
    if (!items.length) {
      return "";
    }
    return `
      <details class="facet-group" ${selected.length ? "open" : ""}>
        <summary>
          <span>${escapeHtml(label)}</span>
          <small>${escapeHtml(String(selected.length || baseItems.length))}${selected.length ? " selected" : ""}</small>
        </summary>
        <div class="facet-buttons">
          ${items
            .map((item) => {
              const active = (this._mapFilters?.[key] || []).includes(item.value);
              return `
                <button
                  type="button"
                  class="facet-chip ${active ? "active" : ""}"
                  data-map-filter-key="${escapeAttr(key)}"
                  data-map-filter-value="${escapeAttr(item.value)}"
                  title="${escapeAttr(item.value)}"
                >
                  <span>${escapeHtml(item.label || item.value)}</span>
                  <strong>${escapeHtml(String(item.count))}</strong>
                </button>
              `;
            })
            .join("")}
        </div>
      </details>
    `;
  }

  _selectedMapFilters() {
    const labelByKey = new Map(MAP_HA_FILTERS);
    const entries = Object.entries(this._mapFilters || {}).flatMap(([key, values]) =>
      (Array.isArray(values) ? values : []).map((value) => ({ key, value }))
    );
    if (!entries.length) {
      return "";
    }
    return `
      <div class="selected-filters">
        ${entries
          .map(
            ({ key, value }) => `
              <button
                type="button"
                class="facet-chip active"
                data-map-filter-key="${escapeAttr(key)}"
                data-map-filter-value="${escapeAttr(value)}"
                title="${escapeAttr(value)}"
              >
                <span>${escapeHtml(`${labelByKey.get(key) || key}: ${friendlyFacetLabel(value)}`)}</span>
              </button>
            `
          )
          .join("")}
      </div>
    `;
  }

  _mapVisual(map, nodes) {
    if (typeof map?.svg === "string" && map.svg) {
      return `<img class="map-image" alt="Home Graph knowledge map" src="${escapeAttr(svgDataUrl(map.svg))}">`;
    }
    if (!nodes.length) {
      return `<p class="empty">No map loaded</p>`;
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
      this._triageSeenIssueIds = new Set();
      this._triageProgress = {
        total,
        processed: 0,
        reviewed: 0,
        remaining: total,
        batches: 0,
        insight: "",
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
      insight: "",
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
          force: options.force ? true : undefined,
        },
        { quiet: true, recordResult: true, suppressError: true }
      );
      this._triageSummary = result || null;
      if (result?.ok === false) {
        this._triageProgress = {
          ...progress,
          insight: result.error || "Automatic review triage failed.",
        };
        return;
      }
      const processed = Number(result?.processed) || 0;
      const reviewed = Number(result?.reviewed) || 0;
      const remaining = Number(result?.remaining);
      const processedIssueIds = Array.isArray(result?.processedIssueIds)
        ? result.processedIssueIds
        : [];
      processedIssueIds.forEach((id) => this._triageSeenIssueIds.add(String(id)));
      this._triageProgress = {
        ...progress,
        processed: Math.min(progress.total || processed, progress.processed + processed),
        reviewed: progress.reviewed + reviewed,
        remaining: Number.isFinite(remaining) ? remaining : progress.remaining,
        batches: progress.batches + 1,
        currentBatch: 0,
        insight: triageInsight(result),
      };
      if ((Number(result?.reviewed) || 0) > 0) {
        await this._call("issues", OPEN_ISSUES_PAYLOAD, { quiet: true });
        await this._call("browse", {}, { quiet: true });
        this._selectedReviewIds.clear();
        this._lastTriageSignature = itemsFromPayload(this._issues, ["issues"])
          .map((issue) => issueKey(issue))
          .sort()
          .join("|");
      }
      shouldContinue =
        processed > 0 &&
        (this._triageProgress.remaining || itemsFromPayload(this._issues, ["issues"]).length) > 0 &&
        this._triageSeenIssueIds.size < (this._triageProgress.total || 0);
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
          ${
            tasks.length
              ? `<div class="task-list" data-scroll-region="refinement-tasks">${tasks.map((task) => this._taskCard(task)).join("")}</div>`
              : `<p class="empty">No refinement tasks</p>`
          }
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
      task?.blockedReason,
    ]
      .filter(Boolean)
      .join(" - ");
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
        ${
          canCancel
            ? `<button type="button" data-action="refinement_cancel" data-task-id="${escapeAttr(String(id))}"><ha-icon icon="mdi:cancel"></ha-icon><span>Cancel</span></button>`
            : ""
        }
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
          ${
            selected.length
              ? this._reviewForm(selected)
              : `<p class="empty">No issue selected</p>`
          }
        </article>
      </section>
      ${this._resultPanel()}
    `;
  }

  _renderPages() {
    const pages = this._generatedPages();
    return `
      <section class="grid two">
        <article class="panel">
          <div class="panel-heading">
            <h2>Automatic Pages</h2>
            <div class="mini-actions">
              <button type="button" data-action="sync"><ha-icon icon="mdi:sync"></ha-icon><span>Sync</span></button>
            </div>
          </div>
          ${
            pages.length
              ? `<div class="page-list" data-scroll-region="generated-pages">${pages.map((page) => this._pageCard(page)).join("")}</div>`
              : `<p class="empty">No automatic pages yet</p>`
          }
        </article>
        <article class="panel">
          <h2>Preview</h2>
          ${this._markdownPreview()}
        </article>
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

  _generatedPages() {
    const pages = itemsFromPayload(this._pages, ["pages"]);
    if (pages.length) {
      return pages.sort(compareGeneratedPages);
    }
    const byId = new Map();
    for (const source of [
      ...itemsFromPayload(this._sources, ["sources"]),
      ...itemsFromPayload(this._browse, ["sources"]),
    ]) {
      if (!isGeneratedPageSource(source)) {
        continue;
      }
      const id = source?.id || source?.sourceId || JSON.stringify(source);
      byId.set(String(id), source);
    }
    return Array.from(byId.values()).sort(compareGeneratedPages);
  }

  _pageCard(page) {
    const source = page?.source || page;
    const metadata = source?.metadata && typeof source.metadata === "object" ? source.metadata : {};
    const title = source?.title || source?.name || source?.sourceUri || source?.id || "Generated page";
    const projection = metadata.projectionKind || metadata.kind || source?.sourceType || "page";
    const regeneration = metadata.regeneration || "automatic";
    const generatedAt = formatTimestamp(metadata.generatedAt || source?.updatedAt || source?.createdAt);
    const detail = [projectionLabel(projection), regeneration, generatedAt].filter(Boolean).join(" - ");
    return `
      <div class="page-card">
        <ha-icon icon="${pageIcon(projection)}"></ha-icon>
        <div>
          <strong>${escapeHtml(String(title))}</strong>
          <span>${escapeHtml(detail)}</span>
          <small>${escapeHtml(String(source?.id || source?.sourceId || ""))}</small>
          ${source?.sourceUri ? `<small>${escapeHtml(String(source.sourceUri))}</small>` : ""}
          ${page?.artifact?.id ? `<small>${escapeHtml(String(page.artifact.id))}</small>` : ""}
        </div>
        <details>
          <summary>Details</summary>
          <pre>${escapeHtml(JSON.stringify(page, null, 2))}</pre>
          ${page?.markdown ? `<pre>${escapeHtml(String(page.markdown))}</pre>` : ""}
        </details>
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
        ${
          items.length
            ? `<div class="list" data-scroll-region="${escapeAttr(`list:${title}`)}">${items.map((item) => this._listItem(item)).join("")}</div>`
            : `<p class="empty">No items</p>`
        }
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
        ${
          issues.length
            ? `<div class="issue-list" data-scroll-region="review-issues">${issues.map((issue) => this._issueButton(issue, selected)).join("")}</div>`
            : `<p class="empty">No open issues</p>`
        }
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
        reviewed
          ? `GoodVibes auto-reviewed ${reviewed} issue(s) in the last batch.`
          : "GoodVibes checked the last batch; those issues still need review."
      );
    }
    const message = reviewed
      ? `GoodVibes auto-reviewed ${reviewed} issue(s); ${remaining} still need review.`
      : `GoodVibes checked the review queue; ${remaining} issue(s) still need review.`;
    return `<div class="notice">${escapeHtml(message)}</div>`;
  }

  _triageProgressNotice(message) {
    const progress = this._triageProgress;
    if (!progress) {
      return `<div class="notice">${escapeHtml(message)}</div>`;
    }
    const total = Math.max(Number(progress.total) || 0, 1);
    const processed = Math.min(Number(progress.processed) || 0, total);
    const percent = Math.max(0, Math.min(100, Math.round((processed / total) * 100)));
    const detail = [
      `${processed}/${total} checked`,
      `${Number(progress.reviewed) || 0} auto-reviewed`,
      `${Number(progress.remaining) || 0} still open`,
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
      this._issues?.result?.total,
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
    const status = [issue.severity, issue.code, issue.status]
      .filter(Boolean)
      .join(" - ");
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
    const heading = bulk
      ? `Add the same manual or source to ${selected.length} selected issues`
      : "Add the missing manual or source";
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
    const sources = itemsFromPayload(this._sources, ["sources"]).filter((source) =>
      source?.id || source?.sourceId
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
      issueId: removeTarget ? undefined : issue.id || issue.issueId,
      sourceId: issue.sourceId,
      nodeId: issue.nodeId,
      action,
      value: semanticReviewValue(issue, fields),
      reviewer: "homeassistant",
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
        quiet: true,
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
      results,
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
      return thinking
        ? `<div class="thinking"><ha-icon class="spin" icon="mdi:loading"></ha-icon><span>Thinking through the Home Graph...</span></div>`
        : `<p class="empty">No answer</p>`;
    }
    const confidence = formatConfidence(answer.confidence);
    const meta = [
      answer.synthesized === true ? "Synthesized" : "",
      answer.mode ? `Mode: ${answer.mode}` : "",
      confidence ? `Confidence: ${confidence}` : "",
      Array.isArray(answer.refinementTaskIds) && answer.refinementTaskIds.length
        ? `${answer.refinementTaskIds.length} refinement task(s)`
        : "",
    ].filter(Boolean);
    const refinementTasks = Array.isArray(answer.refinementTaskIds)
      ? answer.refinementTaskIds.map((id) => ({ id, title: `Refinement task ${id}` }))
      : [];
    return `
      <div class="answer answer-card">
        ${thinking ? `<div class="thinking inline"><ha-icon class="spin" icon="mdi:loading"></ha-icon><span>Updating answer...</span></div>` : ""}
        ${meta.length ? `<div class="answer-meta">${meta.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
        <div class="answer-text">${escapeHtml(String(text))}</div>
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
      const source = page.source || {};
      const title = source.title || source.id || "Generated page";
      return `<div class="answer"><h3>${escapeHtml(String(title))}</h3><pre>${escapeHtml(
        String(page.markdown)
      )}</pre></div>`;
    }
    const result = this._lastResult.result || this._lastResult;
    return result?.markdown
      ? `<div class="answer">${escapeHtml(result.markdown)}</div>`
      : `<p class="empty">No generated content</p>`;
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
    return [status, readiness, issueCount ? `${issueCount} issue(s)` : ""]
      .filter(Boolean)
      .join(" - ");
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
      .map-filters {
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        display: grid;
        gap: 12px;
        margin-bottom: 12px;
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
      .map-canvas {
        background: var(--primary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        min-height: 520px;
        overflow: auto;
      }
      .map-image {
        display: block;
        height: auto;
        min-width: 900px;
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
        max-height: 560px;
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
        padding: 12px;
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
      .page-card details {
        grid-column: 1 / -1;
      }
      .page-tools form {
        margin-top: 12px;
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
        .inline-form,
        .map-form,
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
}

function textInput(name, label, type = "text") {
  return `<label><span>${label}</span><input name="${name}" type="${type}" autocomplete="off"></label>`;
}

function svgDataUrl(svg) {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(String(svg))}`;
}

function isGeneratedPageSource(source) {
  const metadata = source?.metadata && typeof source.metadata === "object" ? source.metadata : {};
  const tags = Array.isArray(source?.tags) ? source.tags.map((tag) => String(tag)) : [];
  return (
    metadata.homeGraphGeneratedPage === true ||
    metadata.homeGraphSourceKind === "generated-page" ||
    Boolean(metadata.projectionKind) ||
    tags.includes("generated-page")
  );
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
  return String(value || "page")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
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
    "failed",
  ];
  return states
    .map((state) => {
      const label = state ? projectionLabel(state) : "Any state";
      return `<option value="${escapeAttr(state)}" ${state === selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");
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
      reviewActionOption("forget", "Remove linked graph item", selected),
    ].join("");
  }
  if (count === 1 && isBatteryIssue(issue)) {
    return [
      reviewActionOption("reject", "Does not use batteries", selected),
      reviewActionOption("accept", "Needs a battery type", selected),
      reviewActionOption("resolve", "Mark resolved", selected),
      reviewActionOption("edit", "Save note or correction", selected),
      reviewActionOption("forget", "Remove linked graph item", selected),
    ].join("");
  }
  return [
    reviewActionOption("accept", "This issue is real", selected),
    reviewActionOption("reject", "Not applicable or incorrect", selected),
    reviewActionOption("resolve", "Fixed already", selected),
    reviewActionOption("edit", "Add note or correction", selected),
    reviewActionOption("forget", "Remove linked graph item", selected),
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
  const source =
    sourceResult?.source ||
    sourceResult?.result?.source ||
    sourceResult?.sources?.[0] ||
    sourceResult?.result?.sources?.[0] ||
    {};
  return String(
    fields?.sourceId ||
      source?.id ||
      source?.sourceId ||
      sourceResult?.sourceId ||
      sourceResult?.result?.sourceId ||
      sourceResult?.id ||
      ""
  );
}

function sourceLinkedReviewValue(sourceId, relation) {
  const value = {
    category: "source_linked",
    relation,
    reason: "Linked a manual/source to this Home Graph object.",
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
  const categories = new Map();
  decisions.forEach((decision) => {
    const category = String(decision?.category || "").trim();
    if (!category) {
      return;
    }
    categories.set(category, (categories.get(category) || 0) + 1);
  });
  const topCategories = Array.from(categories.entries())
    .sort((left, right) => right[1] - left[1])
    .slice(0, 3)
    .map(([category, count]) => `${category} (${count})`)
    .join(", ");
  return [
    `Last batch: ${processed} checked, ${reviewed} auto-reviewed, ${kept} kept for review, ${skipped} already classified.`,
    topCategories ? `Top categories: ${topCategories}.` : "",
  ]
    .filter(Boolean)
    .join(" ");
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
        ...(value.fact || {}),
        batteryPowered: false,
        batteryType: "none",
      };
      value.reason = value.reason || "This Home Graph object does not use batteries.";
    } else if (code.endsWith("missing_manual")) {
      value.fact = {
        ...(value.fact || {}),
        manualRequired: false,
      };
      value.reason = value.reason || "This Home Graph object does not need a manual.";
    }
  }
  return Object.keys(value).length ? value : undefined;
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
  return value === undefined || value === null ? "" : String(value);
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
    readiness.openIssueCount !== undefined ? `${readiness.openIssueCount} open issue(s)` : "",
    readiness.activeRefinementTaskCount !== undefined
      ? `${readiness.activeRefinementTaskCount} active task(s)`
      : "",
    readiness.needsReviewTaskCount !== undefined
      ? `${readiness.needsReviewTaskCount} needs review`
      : "",
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
    review: "Applying review decisions",
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
    `${readiness.needsReviewTaskCount ?? needsReview} needs review`,
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
    "budgetExhausted",
  ];
  return keys.some((key) => result[key] !== undefined) ? result : null;
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
  if (result.scanned !== undefined || result.reparsed !== undefined) {
    return "Reindex Summary";
  }
  if (result.candidateGaps !== undefined || result.processedGaps !== undefined) {
    return "Refinement Summary";
  }
  if (result.reviewed !== undefined) {
    return "Review Summary";
  }
  if (result.pages !== undefined) {
    return "Pages Summary";
  }
  return "Result Summary";
}

function operationSummaryFields(result) {
  const generated = result.generated && typeof result.generated === "object" ? result.generated : {};
  const semantic = result.semantic && typeof result.semantic === "object" ? result.semantic : {};
  const selfImprovement =
    semantic.selfImprovement && typeof semantic.selfImprovement === "object"
      ? semantic.selfImprovement
      : {};
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
    ["Sources", Array.isArray(result.sources) ? result.sources.length : undefined],
    ["Failures", Array.isArray(result.failures) ? result.failures.length : undefined],
    ["Quality Issues", Array.isArray(result.qualityIssues) ? result.qualityIssues.length : undefined],
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
    ["Task IDs", Array.isArray(result.taskIds) ? result.taskIds.length : Array.isArray(selfImprovement.taskIds) ? selfImprovement.taskIds.length : undefined],
    ["Reviewed", result.reviewed],
  ].filter(([, value]) => value !== undefined && value !== "");
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
    ["Task IDs", Array.isArray(result.taskIds) ? result.taskIds.length : undefined],
  ].filter(([, value]) => value !== undefined && value !== "");
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
  return typeof value === "boolean" ? (value ? "yes" : "no") : value;
}

function issueKey(issue) {
  return String(
    issue?.id ||
      issue?.issueId ||
      issue?.nodeId ||
      issue?.sourceId ||
      issue?.message ||
      JSON.stringify(issue || {})
  );
}

function issueTitle(issue) {
  return String(
    issue?.title ||
      issue?.message ||
      issue?.code ||
      issue?.id ||
      issue?.issueId ||
      "Home Graph issue"
  );
}

function issueMessage(issue) {
  const parts = [
    issue?.message && issue?.title ? issue.message : undefined,
    issue?.nodeId ? `Node ${issue.nodeId}` : undefined,
    issue?.sourceId ? `Source ${issue.sourceId}` : undefined,
  ].filter(Boolean);
  return parts.length ? parts.join(" - ") : issue?.id || "";
}

function isOpenIssue(issue) {
  return String(issue?.status || "open").toLowerCase() === "open";
}

function isMissingSourceIssue(issue) {
  const text = [issue?.code, issue?.title, issue?.message]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return (
    text.includes("missing_manual") ||
    text.includes("no linked manual") ||
    text.includes("no linked source")
  );
}

function isSourceResolvableIssue(issue) {
  return Boolean(issue?.nodeId) && isMissingSourceIssue(issue);
}

function isBatteryIssue(issue) {
  const text = [issue?.code, issue?.title, issue?.message]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
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

function recordTitle(record) {
  if (record === null || typeof record !== "object") {
    return String(record ?? "Record");
  }
  return String(
    record?.title ||
      record?.name ||
      record?.sourceUri ||
      record?.canonicalUri ||
      record?.id ||
      "Record"
  );
}

function recordSubtitle(record) {
  if (record === null || typeof record !== "object") {
    return "";
  }
  const metadata = record?.metadata && typeof record.metadata === "object" ? record.metadata : {};
  return [
    record?.kind || record?.sourceType || metadata.semanticKind,
    record?.summary,
    record?.sourceUri || record?.canonicalUri,
    record?.id,
  ]
    .filter(Boolean)
    .map((item) => String(item))
    .join(" - ");
}

function normalizeAnswerPayload(payload) {
  const result = payload?.result && typeof payload.result === "object" ? payload.result : payload || {};
  const answer = result?.answer && typeof result.answer === "object" ? result.answer : {};
  return {
    text: answer.text || result.text || "",
    mode: answer.mode ?? result.mode,
    confidence: answer.confidence ?? result.confidence,
    synthesized: answer.synthesized ?? result.synthesized,
    refinementTaskIds: arrayField(answer.refinementTaskIds ?? result.refinementTaskIds),
    facts: arrayField(answer.facts ?? result.facts),
    gaps: arrayField(answer.gaps ?? result.gaps),
    sources: arrayField(answer.sources ?? result.sources),
    linkedObjects: arrayField(answer.linkedObjects ?? result.linkedObjects),
  };
}

function arrayField(value) {
  return Array.isArray(value) ? value : [];
}

function formatConfidence(value) {
  if (value === undefined || value === null || value === "") {
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
      record.title ||
        record.name ||
        record.summary ||
        record.text ||
        record.question ||
        record.sourceUri ||
        record.url ||
        record.id ||
        "Record"
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
    record.sourceUri || record.url || record.canonicalUri,
  ]
    .filter(Boolean)
    .map((item) => shortText(String(item), 140))
    .join(" - ");
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
    element &&
      ["INPUT", "SELECT", "TEXTAREA"].includes(element.tagName)
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

function facetItems(values) {
  if (!values) {
    return [];
  }
  if (Array.isArray(values)) {
    return values
      .map((item) => {
        if (item && typeof item === "object") {
          const value = String(item.value ?? item.id ?? item.key ?? "");
          return {
            value,
            label: facetItemLabel(item, value),
            count: Number(item.count) || 0,
          };
        }
        const value = String(item ?? "");
        return { value, label: friendlyFacetLabel(value), count: 0 };
      })
      .filter((item) => item.value);
  }
  if (typeof values === "object") {
    return Object.entries(values)
      .map(([value, count]) => ({
        value,
        label: friendlyFacetLabel(value),
        count: Number(count) || 0,
      }))
      .filter((item) => item.value)
      .sort((left, right) => right.count - left.count || left.value.localeCompare(right.value));
  }
  return [];
}

function facetItemLabel(item, value) {
  const metadata = item.metadata && typeof item.metadata === "object" ? item.metadata : {};
  const ha = metadata.homeAssistant && typeof metadata.homeAssistant === "object"
    ? metadata.homeAssistant
    : {};
  return String(
    item.label ||
      item.title ||
      item.name ||
      item.displayName ||
      item.friendlyName ||
      ha.name ||
      ha.friendlyName ||
      friendlyFacetLabel(value)
  );
}

function friendlyFacetLabel(value) {
  const text = String(value || "");
  if (/^[a-f0-9]{16,}$/i.test(text) || /^[a-f0-9]{8,}_.+/i.test(text)) {
    return `${text.slice(0, 8)}...`;
  }
  return text.replace(/_/g, " ");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

customElements.define("goodvibes-home-panel", GoodVibesHomePanel);
