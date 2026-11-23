/*
 * Technische Alternative C.M.I. Schema - schema view for Home Assistant
 *
 *   <ta-cmi-schema-view>        one schema page, drawn like the C.M.I. web page
 *   <ta-cmi-schema-card>        Lovelace card   (type: custom:ta-cmi-schema-card, page: 5)
 *   <ta-cmi-schema-panel>       sidebar dashboard "T.A. Schema" with one tab per page
 *
 * Data comes from the integration (websocket ta_cmi_schema/*), so the C.M.I.
 * login never reaches the browser and it works remotely / in the app.
 */

const POLL_SECONDS = 15;
const MIN_POLL_SECONDS = 10;

// pictures never change - keep them for the whole browser session
const imageCache = new Map();
const imageReady = new Map();

// sets the picture right away when it is known (no flicker on refresh)
function setImage(img, hass, entryId, name, onError) {
  const key = `${entryId}|${name}`;
  if (imageReady.has(key)) {
    img.src = imageReady.get(key);
    return;
  }
  loadImage(hass, entryId, name)
    .then((src) => (img.src = src))
    .catch(() => onError && onError());
}

function loadImage(hass, entryId, name) {
  const key = `${entryId}|${name}`;
  if (!imageCache.has(key)) {
    const promise = hass
      .callWS({ type: "ta_cmi_schema/file", entry_id: entryId, name })
      .then((res) => {
        const src = `data:${res.mime};base64,${res.data}`;
        imageReady.set(key, src);
        return src;
      })
      .catch((err) => {
        imageCache.delete(key);
        throw err;
      });
    imageCache.set(key, promise);
  }
  return imageCache.get(key);
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) node.append(child);
  return node;
}

// relevant parts of the C.M.I. style/schema.css plus Home Assistant touches
const VIEW_CSS = `
:host { display: block; position: relative; }
.wrap { position: relative; width: 100%; overflow: hidden; }
.stage {
  position: absolute; top: 0; left: 0;
  transform-origin: 0 0;
  font-family: Arial, "DejaVu Sans", sans-serif;
  color: #000;
}
.bgimg { position: absolute; top: 0; left: 0; pointer-events: none; user-select: none; }
#values { position: absolute; top: 0; left: 0; text-align: left; z-index: 10; }
#values > div { white-space: nowrap; }
.hide { display: none; }
.durchsichtig { opacity: 0; background-color: #fff; cursor: pointer; }
.v0, .v1 { display: block; width: 100%; height: 100%; overflow: hidden; border-radius: 4px; }
#values > div:not(.visible1) > .v1 { display: none; }
#values > div.visible1 > .v0 { display: none; }
.cent { display: inline-block; position: relative; top: 50%; transform: translateY(-50%); }
.bord { border: solid 1px #000; border-radius: 5px; box-sizing: content-box; }
.buttonx2, .taster { text-align: center; }
.buttonx2.visible-1, .taster.visible-1 { display: none; }
.buttonx2.visible-2, .taster.visible-2 { opacity: .45; cursor: not-allowed; }
.click { cursor: pointer; user-select: none; -webkit-user-select: none; }
.click:hover { outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 2px; border-radius: 4px; }
.durchsichtig.click:hover { outline: none; opacity: .15; background-color: var(--primary-color, #03a9f4); }
.busy { opacity: .5; }
.msg {
  padding: 16px; color: var(--secondary-text-color, #666);
  font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
}
.msg.error { color: var(--error-color, #db4437); }
`;

class TaCmiSchemaView extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.fit = "width"; // "width" (card) or "contain" (dashboard)
    this._data = null;
    this._error = null;
    this._timer = null;
    this._loading = false;
    this._entityStates = new Map();
    this._resize = new ResizeObserver(() => this._scale());
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first && this._page) this._load();
    else this._checkEntities();
  }

  get hass() {
    return this._hass;
  }

  setPage(entryId, page) {
    if (this._entryId === entryId && this._page === page) return;
    this._entryId = entryId;
    this._page = page;
    this._data = null;
    this._error = null;
    this._render();
    if (this._hass) this._load();
  }

  connectedCallback() {
    this._resize.observe(this);
    this._startTimer();
    if (this._hass && this._page && !this._data) this._load();
  }

  disconnectedCallback() {
    this._resize.disconnect();
    clearInterval(this._timer);
    this._timer = null;
    this._stopTaster();
  }

  _startTimer() {
    clearInterval(this._timer);
    const refresh = Math.max(
      MIN_POLL_SECONDS,
      Math.min(POLL_SECONDS, (this._data && this._data.refresh) || POLL_SECONDS)
    );
    this._timer = setInterval(() => {
      if (document.visibilityState === "visible" && this.isConnected) this._load();
    }, refresh * 1000);
  }

  // an entity of this page changed (e.g. edited in the more-info dialog) -> reload
  _checkEntities() {
    if (!this._data || !this._hass) return;
    let changed = false;
    for (const item of this._data.elements) {
      if (!item.entity) continue;
      const state = this._hass.states[item.entity];
      const stamp = state ? state.last_updated : null;
      if (this._entityStates.has(item.entity) && this._entityStates.get(item.entity) !== stamp) {
        changed = true;
      }
      this._entityStates.set(item.entity, stamp);
    }
    if (changed) {
      clearTimeout(this._reloadSoon);
      this._reloadSoon = setTimeout(() => this._load(true), 300);
    }
  }

  async _load(fresh = false) {
    if (!this._hass || !this._page || this._loading) return;
    this._loading = true;
    const page = this._page;
    try {
      const msg = { type: "ta_cmi_schema/page", page, fresh };
      if (this._entryId) msg.entry_id = this._entryId;
      const data = await this._hass.callWS(msg);
      if (page !== this._page) return;
      const firstLoad = !this._data;
      this._data = data;
      this._error = null;
      if (!this._entryId) this._entryId = data.entry_id;
      this._render();
      if (firstLoad) this._startTimer();
      this.dispatchEvent(
        new CustomEvent("ta-page-loaded", { detail: { name: data.name, page }, bubbles: true, composed: true })
      );
    } catch (err) {
      if (page !== this._page) return;
      this._error = (err && err.message) || String(err);
      if (!this._data) this._render();
    } finally {
      this._loading = false;
    }
  }

  _render() {
    const root = this.shadowRoot;
    root.innerHTML = "";
    root.append(el("style", { text: VIEW_CSS }));
    if (!this._data) {
      const text = this._error
        ? `C.M.I.: ${this._error}`
        : this._page
          ? "Schema wird geladen …"
          : "Keine Seite gewählt";
      root.append(el("div", { class: this._error ? "msg error" : "msg", text }));
      return;
    }
    const data = this._data;
    root.append(el("style", { text: data.css || "" }));

    const stage = el("div", { class: "stage" });
    stage.style.width = `${data.width}px`;
    stage.style.height = `${data.height}px`;
    stage.style.backgroundColor = data.background || "#fff";

    if (data.image) {
      const bg = el("img", { class: "bgimg", alt: "" });
      bg.style.width = `${data.width}px`;
      bg.style.height = `${data.height}px`;
      setImage(bg, this._hass, data.entry_id, data.image, () => bg.remove());
      stage.append(bg);
    }

    const values = el("div", { id: "values" });
    for (const item of data.elements) values.append(this._element(item, data));
    stage.append(values);

    const wrap = el("div", { class: "wrap" }, [stage]);
    root.append(wrap);
    this._wrap = wrap;
    this._stage = stage;
    this._scale();
  }

  _element(item, data) {
    const node = el("div", { id: item.pos, class: item.cls.join(" ") });
    if (item.spans && item.spans.length) {
      for (const [cls, text] of item.spans) {
        node.append(el("span", { class: cls }, [el("span", { class: "cent", text })]));
      }
    } else if (item.imgs && item.imgs.length) {
      const shown = this._shownImage(item);
      for (const img of item.imgs) {
        const pic = el("img", { alt: "" });
        if (img.bis !== null && img.bis !== undefined) pic.setAttribute("bis", img.bis);
        const visible = shown === null ? !img.hide : img === shown;
        if (!visible) pic.classList.add("hide");
        setImage(pic, this._hass, data.entry_id, img.name);
        node.append(pic);
      }
    } else if (item.text) {
      node.textContent = item.text;
    }

    const locked = item.visible !== null && item.visible < -1;
    if (item.action === "link" && item.link) {
      node.classList.add("click");
      node.title = `Seite ${item.link}`;
      node.addEventListener("click", () =>
        this.dispatchEvent(
          new CustomEvent("ta-navigate", { detail: { page: item.link }, bubbles: true, composed: true })
        )
      );
    } else if (item.action === "press" && !locked) {
      node.classList.add("click");
      node.addEventListener("click", () => this._press(item, node));
    } else if (item.action === "taster" && !locked) {
      node.classList.add("click");
      node.addEventListener("pointerdown", (ev) => {
        ev.preventDefault();
        this._startTaster(item, node);
      });
    } else if (item.entity) {
      node.classList.add("click");
      node.addEventListener("click", () =>
        this.dispatchEvent(
          new CustomEvent("hass-more-info", { detail: { entityId: item.entity }, bubbles: true, composed: true })
        )
      );
    }
    return node;
  }

  // same rule as showImg() of the C.M.I. page: the first picture whose "bis"
  // is not below the current value wins, otherwise the default picture
  _shownImage(item) {
    if (item.visible === null || item.visible === undefined) return null;
    for (const img of item.imgs) {
      if (img.bis !== null && img.bis !== undefined && item.visible <= img.bis) return img;
    }
    return null;
  }

  async _press(item, node, value) {
    node.classList.add("busy");
    try {
      const msg = { type: "ta_cmi_schema/press", page: this._page, pos: item.pos };
      if (this._entryId) msg.entry_id = this._entryId;
      if (value !== undefined) msg.value = value;
      await this._hass.callWS(msg);
    } catch (err) {
      this._toast(`C.M.I.: ${(err && err.message) || err}`);
    } finally {
      node.classList.remove("busy");
    }
    if (value === undefined) {
      this._loading = false;
      await this._load(true);
    }
  }

  // push button: 1 while held (repeated like the C.M.I. page), 0 on release
  _startTaster(item, node) {
    if (this._taster) return;
    node.classList.remove("visible0");
    node.classList.add("visible1");
    const release = () => this._stopTaster();
    this._taster = {
      item,
      node,
      release,
      timer: setInterval(() => this._press(item, node, 1), 2000),
    };
    window.addEventListener("pointerup", release);
    window.addEventListener("pointercancel", release);
    this._press(item, node, 1);
  }

  _stopTaster() {
    const taster = this._taster;
    if (!taster) return;
    this._taster = null;
    clearInterval(taster.timer);
    window.removeEventListener("pointerup", taster.release);
    window.removeEventListener("pointercancel", taster.release);
    if (this._hass) {
      this._press(taster.item, taster.node, 0).then(() => setTimeout(() => this._load(true), 250));
    }
  }

  _toast(message) {
    this.dispatchEvent(
      new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true })
    );
  }

  _scale() {
    if (!this._data || !this._wrap || !this._stage) return;
    const { width, height } = this._data;
    const availW = this.clientWidth || width;
    let scale = availW / width;
    if (this.fit === "contain") {
      const availH = this.clientHeight || height;
      scale = Math.min(scale, availH / height);
    }
    scale = Math.max(scale, 0.05);
    this._stage.style.transform = `scale(${scale})`;
    this._wrap.style.width = `${width * scale}px`;
    this._wrap.style.height = `${height * scale}px`;
    if (this.fit === "contain") this._wrap.style.margin = "0 auto";
  }
}

/* ------------------------------------------------------------------ card */

class TaCmiSchemaCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("ta-cmi-schema-card-editor");
  }

  static getStubConfig() {
    return { page: 1 };
  }

  setConfig(config) {
    if (!config || !config.page) throw new Error("Bitte eine Schemaseite angeben (page: 1)");
    this._config = config;
    if (!this._card) {
      this._card = document.createElement("ha-card");
      this._view = document.createElement("ta-cmi-schema-view");
      this._view.addEventListener("ta-navigate", (ev) => {
        ev.stopPropagation();
        if (this._config.navigation !== false) {
          this._view.setPage(this._config.entry_id, ev.detail.page);
          this._renderHeader(null);
        }
      });
      this._view.addEventListener("ta-page-loaded", (ev) => {
        ev.stopPropagation();
        this._renderHeader(ev.detail.page !== Number(this._config.page) ? ev.detail : null);
      });
      this._card.append(this._view);
      this.append(this._card);
    }
    this._card.header = config.title || undefined;
    this._view.setPage(config.entry_id, Number(config.page));
  }

  // after following a link inside the card: way back to the configured page
  _renderHeader(detail) {
    if (this._back) this._back.remove();
    this._back = null;
    if (!detail) return;
    const back = el("div", {
      style:
        "display:flex;align-items:center;gap:8px;padding:6px 12px;cursor:pointer;" +
        "color:var(--primary-color);font-size:14px;",
      text: `← zurück  ·  ${detail.name}`,
    });
    back.addEventListener("click", () => {
      this._view.setPage(this._config.entry_id, Number(this._config.page));
      this._renderHeader(null);
    });
    this._card.prepend(back);
    this._back = back;
  }

  set hass(hass) {
    this._hass = hass;
    if (this._view) this._view.hass = hass;
  }

  getCardSize() {
    return 6;
  }

  getGridOptions() {
    return { columns: "full", min_columns: 6 };
  }
}

class TaCmiSchemaCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      hass
        .callWS({ type: "ta_cmi_schema/pages" })
        .then((entries) => {
          this._entries = entries;
          this._render();
        })
        .catch(() => {});
    }
  }

  _changed(patch) {
    this._config = { ...this._config, ...patch };
    for (const [key, value] of Object.entries(patch)) {
      if (value === "" || value === undefined) delete this._config[key];
    }
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true })
    );
  }

  _render() {
    if (!this._config) return;
    this.innerHTML = "";
    const style =
      "display:block;width:100%;padding:8px;margin:4px 0 12px;font-size:16px;" +
      "background:var(--card-background-color);color:var(--primary-text-color);" +
      "border:1px solid var(--divider-color);border-radius:4px;box-sizing:border-box;";
    const entries = this._entries || [];
    if (entries.length > 1) {
      const select = el("select", { style });
      select.append(el("option", { value: "", text: "Erstes C.M.I." }));
      for (const entry of entries) {
        const opt = el("option", { value: entry.entry_id, text: entry.title });
        if (entry.entry_id === this._config.entry_id) opt.selected = true;
        select.append(opt);
      }
      select.addEventListener("change", () => this._changed({ entry_id: select.value }));
      this.append(el("label", { text: "C.M.I." }), select);
    }
    const entry =
      entries.find((e) => e.entry_id === this._config.entry_id) || entries[0] || { pages: [] };
    const pages = el("select", { style });
    if (!entry.pages.length) pages.append(el("option", { value: this._config.page, text: `Seite ${this._config.page}` }));
    for (const page of entry.pages) {
      const opt = el("option", { value: page.page, text: `${page.page} – ${page.name}` });
      if (Number(this._config.page) === page.page) opt.selected = true;
      pages.append(opt);
    }
    pages.addEventListener("change", () => this._changed({ page: Number(pages.value) }));
    const title = el("input", { style, type: "text", value: this._config.title || "", placeholder: "optional" });
    title.addEventListener("change", () => this._changed({ title: title.value }));
    this.append(el("label", { text: "Schemaseite" }), pages, el("label", { text: "Titel" }), title);
  }
}

/* ------------------------------------------------------------------ sidebar dashboard */

const PANEL_CSS = `
:host {
  display: flex; flex-direction: column; height: 100%;
  background: var(--primary-background-color);
  color: var(--primary-text-color);
  font-family: var(--paper-font-body1_-_font-family, Roboto, "Noto Sans", sans-serif);
}
.toolbar {
  display: flex; align-items: center; gap: 8px;
  height: var(--header-height, 56px); padding: 0 12px; box-sizing: border-box;
  background: var(--app-header-background-color, var(--primary-color));
  color: var(--app-header-text-color, #fff);
  flex: none;
}
.toolbar .title { font-size: 20px; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.toolbar select {
  background: transparent; color: inherit; border: 1px solid rgba(255,255,255,.5);
  border-radius: 4px; padding: 4px; font-size: 14px;
}
.toolbar select option { color: #000; }
.tabs {
  display: flex; gap: 2px; overflow-x: auto; flex: none;
  background: var(--app-header-background-color, var(--primary-color));
  padding: 0 8px; scrollbar-width: thin;
}
.tab {
  flex: none; padding: 10px 14px; cursor: pointer; white-space: nowrap; font-size: 14px;
  color: var(--app-header-text-color, #fff); opacity: .75;
  border-bottom: 3px solid transparent; background: none; border-top: 0; border-left: 0; border-right: 0;
  font-family: inherit;
}
.tab:hover { opacity: 1; }
.tab.active { opacity: 1; border-bottom-color: var(--app-header-text-color, #fff); font-weight: 500; }
.content {
  flex: 1; min-height: 0; padding: 12px; box-sizing: border-box;
  display: flex; flex-direction: column;
}
ta-cmi-schema-view {
  flex: 1; min-height: 0;
  border-radius: var(--ha-card-border-radius, 12px);
  overflow: hidden;
}
.msg { padding: 24px; color: var(--secondary-text-color); }
@media (max-width: 600px) { .content { padding: 4px; } }
`;

class TaCmiSchemaPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._entries = null;
    this._hashListener = () => this._fromHash();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (this._menu) this._menu.hass = hass;
    if (this._view) this._view.hass = hass;
    if (first) this._init();
  }

  set narrow(narrow) {
    this._narrow = narrow;
    if (this._menu) this._menu.narrow = narrow;
  }

  set panel(panel) {
    this._panel = panel;
  }

  set route(route) {
    this._route = route;
  }

  connectedCallback() {
    window.addEventListener("hashchange", this._hashListener);
  }

  disconnectedCallback() {
    window.removeEventListener("hashchange", this._hashListener);
  }

  async _init() {
    this._build();
    try {
      this._entries = await this._hass.callWS({ type: "ta_cmi_schema/pages" });
    } catch (err) {
      this._entries = [];
      this._message(`C.M.I.: ${(err && err.message) || err}`);
      return;
    }
    if (!this._entries.length || !this._entries.some((e) => e.pages.length)) {
      this._message("Noch keine Schemaseiten gefunden – bitte „Schema neu einlesen“ drücken.");
      return;
    }
    let stored = null;
    try {
      stored = JSON.parse(localStorage.getItem("ta_cmi_schema_panel") || "null");
    } catch (err) {
      stored = null;
    }
    const hash = this._parseHash();
    const entry =
      this._entries.find((e) => e.entry_id === (hash.entry || (stored && stored.entry))) ||
      this._entries.find((e) => e.pages.length);
    const page =
      entry.pages.find((p) => p.page === (hash.page || (stored && stored.page))) || entry.pages[0];
    this._select(entry.entry_id, page.page);
  }

  _build() {
    const root = this.shadowRoot;
    root.innerHTML = "";
    root.append(el("style", { text: PANEL_CSS }));
    const toolbar = el("div", { class: "toolbar" });
    if (customElements.get("ha-menu-button")) {
      this._menu = document.createElement("ha-menu-button");
      this._menu.hass = this._hass;
      this._menu.narrow = this._narrow;
      toolbar.append(this._menu);
    }
    this._title = el("div", { class: "title", text: "T.A. Schema" });
    toolbar.append(this._title);
    this._entrySelect = el("select");
    this._entrySelect.style.display = "none";
    this._entrySelect.addEventListener("change", () => {
      const entry = this._entries.find((e) => e.entry_id === this._entrySelect.value);
      if (entry && entry.pages.length) this._select(entry.entry_id, entry.pages[0].page);
    });
    toolbar.append(this._entrySelect);
    this._tabs = el("div", { class: "tabs" });
    this._content = el("div", { class: "content" });
    this._view = document.createElement("ta-cmi-schema-view");
    this._view.fit = "contain";
    this._view.hass = this._hass;
    this._view.addEventListener("ta-navigate", (ev) => {
      ev.stopPropagation();
      this._select(this._entryId, ev.detail.page);
    });
    this._content.append(this._view);
    root.append(toolbar, this._tabs, this._content);
  }

  _message(text) {
    this._content.innerHTML = "";
    this._content.append(el("div", { class: "msg", text }));
  }

  _parseHash() {
    const match = /^#(?:([0-9a-zA-Z]+):)?(\d+)$/.exec(window.location.hash || "");
    if (!match) return {};
    return { entry: match[1] || null, page: Number(match[2]) };
  }

  _fromHash() {
    if (!this._entries) return;
    const hash = this._parseHash();
    if (hash.page && (hash.page !== this._page || (hash.entry && hash.entry !== this._entryId))) {
      this._select(hash.entry || this._entryId, hash.page);
    }
  }

  _select(entryId, page) {
    const entry = this._entries.find((e) => e.entry_id === entryId) || this._entries[0];
    this._entryId = entry.entry_id;
    this._page = page;
    const multi = this._entries.length > 1;
    const hash = multi ? `#${entry.entry_id}:${page}` : `#${page}`;
    if (window.location.hash !== hash) history.replaceState(history.state, "", hash);
    try {
      localStorage.setItem("ta_cmi_schema_panel", JSON.stringify({ entry: entry.entry_id, page }));
    } catch (err) {
      /* private mode */
    }

    // C.M.I. selection (only with several C.M.I.)
    this._entrySelect.style.display = multi ? "" : "none";
    this._entrySelect.innerHTML = "";
    for (const e of this._entries) {
      const opt = el("option", { value: e.entry_id, text: e.title });
      if (e.entry_id === entry.entry_id) opt.selected = true;
      this._entrySelect.append(opt);
    }

    this._tabs.innerHTML = "";
    let active = null;
    const pages = entry.pages.some((p) => p.page === page)
      ? entry.pages
      : [...entry.pages, { page, name: `Seite ${page}` }];
    for (const p of pages) {
      const tab = el("button", { class: p.page === page ? "tab active" : "tab", text: p.name });
      tab.addEventListener("click", () => this._select(entry.entry_id, p.page));
      this._tabs.append(tab);
      if (p.page === page) active = tab;
    }
    if (active) active.scrollIntoView({ block: "nearest", inline: "center" });
    const current = pages.find((p) => p.page === page);
    this._title.textContent = current ? `T.A. Schema · ${current.name}` : "T.A. Schema";

    if (!this._content.contains(this._view)) {
      this._content.innerHTML = "";
      this._content.append(this._view);
    }
    this._view.setPage(entry.entry_id, page);
  }
}

/* ------------------------------------------------------------------ register */

const define = (name, cls) => {
  if (!customElements.get(name)) customElements.define(name, cls);
};
define("ta-cmi-schema-view", TaCmiSchemaView);
define("ta-cmi-schema-card", TaCmiSchemaCard);
define("ta-cmi-schema-card-editor", TaCmiSchemaCardEditor);
define("ta-cmi-schema-panel", TaCmiSchemaPanel);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "ta-cmi-schema-card")) {
  window.customCards.push({
    type: "ta-cmi-schema-card",
    name: "T.A. C.M.I. Schema",
    description: "Eine Seite des C.M.I.-Schemas wie im C.M.I. – mit Live-Werten zum Antippen.",
    preview: false,
    documentationURL: "https://github.com/codo70/ha-ta-cmi-schema",
  });
}
