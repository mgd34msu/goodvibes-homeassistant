const DEFAULT_WS_TYPE = "goodvibes/home_graph/call";
const DEFAULT_UPLOAD_URL = "/api/goodvibes/home-graph/upload";

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

class GoodVibesHomePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "browse";
    this._busy = "";
    this._error = "";
    this._status = {};
    this._sources = {};
    this._browse = {};
    this._issues = {};
    this._answer = {};
    this._lastResult = {};
    this._filter = "";
    this._loaded = false;
    this._pendingBackgroundRender = false;
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
      this._call("issues", {}, { quiet: true }),
    ]);
    if (options.background) {
      this._renderAfterBackgroundUpdate();
      return;
    }
    this._render();
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
      this._lastResult = result || {};
      if (action === "status") {
        this._status = result || {};
      } else if (action === "sources") {
        this._sources = result || {};
      } else if (action === "browse") {
        this._browse = result || {};
      } else if (action === "issues") {
        this._issues = result || {};
      } else if (action === "ask") {
        this._answer = result || {};
      }
      return result || {};
    } catch (err) {
      this._error = err?.message || String(err);
      return {};
    } finally {
      if (!options.quiet) {
        this._busy = "";
        this._render();
      }
    }
  }

  async _upload(form) {
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
      await this._refreshAll();
    } catch (err) {
      this._showError(err);
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
      });
    });
    root.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", () => {
        this._handleAction(button.dataset.action).catch((err) => this._showError(err));
      });
    });
    root.querySelectorAll("form[data-form]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._handleForm(form).catch((err) => this._showError(err));
      });
    });
  }

  async _handleAction(action) {
    if (action === "refresh") {
      await this._refreshAll();
      return;
    }
    if (action === "sync") {
      await this._call("sync");
      await this._refreshAll();
    }
  }

  async _handleForm(form) {
    const name = form.dataset.form;
    const fields = this._formValues(form);
    if (name === "ask") {
      await this._call("ask", {
        query: fields.query,
        includeSources: true,
        includeLinkedObjects: true,
      });
      return;
    }
    if (name === "browse") {
      this._filter = fields.query || "";
      await this._call("browse", { limit: fields.limit || 250 });
      return;
    }
    if (name === "url") {
      await this._call("ingest_url", this._ingestPayload(fields, { url: fields.url }));
      await this._refreshAll();
      return;
    }
    if (name === "note") {
      await this._call(
        "ingest_note",
        this._ingestPayload(fields, {
          body: fields.body,
        })
      );
      await this._refreshAll();
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
      await this._refreshAll();
      return;
    }
    if (name === "upload") {
      await this._upload(form);
      return;
    }
    if (name === "link" || name === "unlink") {
      await this._call(name, {
        sourceId: fields.sourceId,
        nodeId: fields.nodeId,
        target: this._targetFromFields(fields),
        metadata: this._jsonFromText(fields.metadata),
      });
      await this._refreshAll();
      return;
    }
    if (name === "review") {
      await this._call("review", {
        issueId: fields.issueId,
        sourceId: fields.sourceId,
        nodeId: fields.nodeId,
        action: fields.action,
        value: this._jsonOrText(fields.value),
        reviewer: "homeassistant",
      });
      await this._refreshAll();
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

  _render() {
    if (!this.shadowRoot) {
      return;
    }
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
            <button type="button" data-action="refresh" title="Refresh">
              <ha-icon icon="mdi:refresh"></ha-icon>
              <span>Refresh</span>
            </button>
            <button type="button" data-action="sync" title="Sync Home Graph">
              <ha-icon icon="mdi:sync"></ha-icon>
              <span>Sync</span>
            </button>
          </div>
        </header>
        <nav class="tabs">
          ${this._tabButton("browse", "mdi:graph-outline", "Browse")}
          ${this._tabButton("ingest", "mdi:tray-arrow-up", "Ingest")}
          ${this._tabButton("ask", "mdi:message-question-outline", "Ask")}
          ${this._tabButton("link", "mdi:link-variant", "Link")}
          ${this._tabButton("review", "mdi:clipboard-edit-outline", "Review")}
          ${this._tabButton("pages", "mdi:file-document-outline", "Pages")}
        </nav>
        ${this._error ? `<div class="notice error">${escapeHtml(this._error)}</div>` : ""}
        ${this._busy ? `<div class="notice">Working: ${escapeHtml(this._busy)}</div>` : ""}
        <main>
          ${this._renderTab()}
        </main>
      </section>
    `;
    this._wireEvents();
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
    if (this._tab === "ask") {
      return this._renderAsk();
    }
    if (this._tab === "link") {
      return this._renderLink();
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
    return `
      <section class="grid two">
        <article class="panel">
          <h2>Ask The House</h2>
          <form data-form="ask">
            <label><span>Question</span><textarea name="query" rows="6"></textarea></label>
            <button type="submit"><ha-icon icon="mdi:message-processing-outline"></ha-icon><span>Ask</span></button>
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

  _renderReview() {
    const issues = this._filtered(itemsFromPayload(this._issues, ["issues"]));
    return `
      <section class="grid two">
        ${this._listPanel("Open Issues", issues)}
        <article class="panel">
          <h2>Review Or Remove</h2>
          <form data-form="review">
            ${textInput("issueId", "Issue ID")}
            ${textInput("sourceId", "Source ID")}
            ${textInput("nodeId", "Node ID")}
            <label>
              <span>Action</span>
              <select name="action">
                <option value="accept">accept</option>
                <option value="reject">reject</option>
                <option value="resolve">resolve</option>
                <option value="edit">edit</option>
                <option value="forget">forget</option>
              </select>
            </label>
            <label><span>Value JSON</span><textarea name="value" rows="4"></textarea></label>
            <button type="submit"><ha-icon icon="mdi:check-decagram-outline"></ha-icon><span>Apply</span></button>
          </form>
        </article>
      </section>
      ${this._resultPanel()}
    `;
  }

  _renderPages() {
    return `
      <section class="grid two">
        <article class="panel">
          <h2>Generate</h2>
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
            <button type="submit"><ha-icon icon="mdi:file-cog-outline"></ha-icon><span>Generate</span></button>
          </form>
        </article>
        <article class="panel">
          <h2>Generated Content</h2>
          ${this._markdownPreview()}
        </article>
      </section>
      ${this._resultPanel()}
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
            ? `<div class="list">${items.map((item) => this._listItem(item)).join("")}</div>`
            : `<p class="empty">No items</p>`
        }
      </article>
    `;
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
    const answerPayload = this._answer.result || this._answer;
    const answer = answerPayload.answer || {};
    const text = answer.text || answerPayload.text || "";
    return text
      ? `<div class="answer">${escapeHtml(String(text))}</div>`
      : `<p class="empty">No answer</p>`;
  }

  _markdownPreview() {
    const result = this._lastResult.result || this._lastResult;
    return result?.markdown
      ? `<div class="answer">${escapeHtml(result.markdown)}</div>`
      : `<p class="empty">No generated content</p>`;
  }

  _resultPanel() {
    return `
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
    const issueCount = itemsFromPayload(this._issues, ["issues"]).length;
    return [status, issueCount ? `${issueCount} issue(s)` : ""]
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
      form {
        display: grid;
        gap: 12px;
      }
      .inline-form {
        align-items: end;
        grid-template-columns: minmax(180px, 1fr) minmax(120px, 220px) auto;
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
      .result {
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        padding: 12px;
      }
      @media (max-width: 860px) {
        .topbar,
        .grid.two,
        .inline-form,
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

function metadataField() {
  return `<label><span>Metadata JSON</span><textarea name="metadata" rows="3"></textarea></label>`;
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
