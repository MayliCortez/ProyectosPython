/*
 * inject.js — Bootstrap del panel flotante de AutoFlow Studio dentro de Google Flow.
 * Construye la UI, conecta el QueueEngine con el FlowAdapter y maneja
 * import de archivos, ajustes, tema y arrastre/redimension del panel.
 *
 * Depende de los globales definidos por los UMD previos: self.AFS.*
 */
(function () {
  "use strict";
  if (window.__afsInjected) return;
  window.__afsInjected = true;

  const AFS = window.AFS || {};
  const { i18n, store, prompts, csv, QueueEngine, FlowAdapter } = AFS;
  const $ = (tag, props, children) => {
    const el = document.createElement(tag);
    if (props) {
      // `dataset` es un getter de solo lectura: se asigna aparte (no via Object.assign).
      const { dataset, ...rest } = props;
      Object.assign(el, rest);
      if (dataset) Object.entries(dataset).forEach(([k, v]) => (el.dataset[k] = v));
    }
    (children || []).forEach((c) => el.appendChild(typeof c === "string" ? document.createTextNode(c) : c));
    return el;
  };

  const MODES = ["text_to_video", "frame_to_video", "ingredients_to_video", "text_to_image", "image_to_image"];

  let settings = store.DEFAULTS;
  let t = i18n.createTranslator(settings.language);
  let engine = null;
  let staged = []; // jobs preparados aun no en el engine

  // ----- Descarga via background -----------------------------------------
  function download(url, options) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: "afs-download", url, options }, (res) => resolve(res));
      } catch (e) {
        resolve({ ok: false, error: String(e) });
      }
    });
  }

  function log(msg) {
    const box = root.querySelector("#afs-log");
    if (!box) return;
    const line = $("div", { className: "afs-log-line", textContent: `[${new Date().toLocaleTimeString()}] ${msg}` });
    box.appendChild(line);
    box.scrollTop = box.scrollHeight;
    while (box.children.length > 200) box.removeChild(box.firstChild);
  }

  // ----- Construccion de la UI -------------------------------------------
  const root = $("div", { id: "afs-root", className: "afs afs-size-medium afs-theme-dark" });

  function buildHeader() {
    const drag = $("div", { className: "afs-header", id: "afs-drag" });
    const title = $("div", { className: "afs-title" }, ["⚡ ", t("title")]);
    const spacer = $("div", { className: "afs-spacer" });
    const btnTheme = $("button", { className: "afs-icon-btn", title: t("theme"), textContent: "🌓" });
    const btnSize = $("button", { className: "afs-icon-btn", title: "size", textContent: "⤢" });
    const btnMin = $("button", { className: "afs-icon-btn", title: "min", textContent: "—" });
    btnTheme.onclick = () => toggleTheme();
    btnSize.onclick = () => cycleSize();
    btnMin.onclick = () => root.classList.toggle("afs-collapsed");
    drag.append(title, spacer, btnTheme, btnSize, btnMin);
    return drag;
  }

  function buildTabs() {
    const tabs = $("div", { className: "afs-tabs" });
    MODES.forEach((m) => {
      const b = $("button", { className: "afs-tab", textContent: t(m), dataset: { mode: m } });
      if (m === settings.mode) b.classList.add("afs-active");
      b.onclick = () => {
        settings.mode = m;
        store.saveSettings({ mode: m });
        tabs.querySelectorAll(".afs-tab").forEach((x) => x.classList.toggle("afs-active", x.dataset.mode === m));
      };
      tabs.appendChild(b);
    });
    return tabs;
  }

  function buildComposer() {
    const wrap = $("div", { className: "afs-composer" });
    const ta = $("textarea", { id: "afs-prompts", className: "afs-textarea", placeholder: t("prompts_placeholder"), rows: 6 });
    const fileInput = $("input", { type: "file", accept: ".txt,.csv,.tsv", style: "display:none", id: "afs-file" });
    fileInput.onchange = onImportFile;

    const btnImport = $("button", { className: "afs-btn afs-ghost", textContent: "📁 " + t("import_file") });
    btnImport.onclick = () => fileInput.click();
    const btnAdd = $("button", { className: "afs-btn afs-primary", textContent: "➕ " + t("add_to_queue") });
    btnAdd.onclick = onAddToQueue;

    const row = $("div", { className: "afs-row" }, [btnImport, btnAdd]);
    wrap.append(ta, fileInput, row);
    return wrap;
  }

  function buildControls() {
    const wrap = $("div", { className: "afs-controls" });
    const mk = (id, label, cls) => $("button", { id, className: "afs-btn " + (cls || ""), textContent: label });
    const start = mk("afs-start", "▶ " + t("start"), "afs-primary");
    const pause = mk("afs-pause", "⏸ " + t("pause"), "afs-ghost");
    const stop = mk("afs-stop", "⏹ " + t("stop"), "afs-danger");
    const clear = mk("afs-clear", "🗑 " + t("clear"), "afs-ghost");
    start.onclick = onStart;
    pause.onclick = onPauseResume;
    stop.onclick = onStop;
    clear.onclick = onClear;
    wrap.append(start, pause, stop, clear);
    return wrap;
  }

  function buildQueue() {
    const wrap = $("div", { className: "afs-queue-wrap" });
    const head = $("div", { className: "afs-section-head" }, [t("queue"), $("span", { id: "afs-counts", className: "afs-counts" })]);
    const list = $("div", { id: "afs-queue", className: "afs-queue" });
    wrap.append(head, list);
    return wrap;
  }

  function buildSettings() {
    const wrap = $("details", { className: "afs-settings" });
    const sum = $("summary", { textContent: "⚙ " + t("settings") });
    wrap.appendChild(sum);
    const grid = $("div", { className: "afs-grid" });

    const select = (label, key, opts) => {
      const s = $("select", { className: "afs-input" });
      opts.forEach(([v, txt]) => {
        const o = $("option", { value: v, textContent: txt });
        if (String(settings[key]) === String(v)) o.selected = true;
        s.appendChild(o);
      });
      s.onchange = () => { settings[key] = s.value; store.saveSettings({ [key]: s.value }); };
      return $("label", { className: "afs-field" }, [$("span", { textContent: label }), s]);
    };
    const number = (label, key, min, max, step) => {
      const inp = $("input", { className: "afs-input", type: "number", min, max, step: step || 1, value: settings[key] });
      inp.onchange = () => { settings[key] = Number(inp.value); store.saveSettings({ [key]: Number(inp.value) }); };
      return $("label", { className: "afs-field" }, [$("span", { textContent: label }), inp]);
    };
    const toggle = (label, key) => {
      const inp = $("input", { type: "checkbox", checked: !!settings[key] });
      inp.onchange = () => { settings[key] = inp.checked; store.saveSettings({ [key]: inp.checked }); };
      return $("label", { className: "afs-field afs-check" }, [inp, $("span", { textContent: label })]);
    };

    grid.append(
      select(t("aspect_ratio"), "aspectRatio", [["16:9","16:9"],["9:16","9:16"],["1:1","1:1"],["3:4","3:4"],["4:3","4:3"]]),
      select(t("duration"), "duration", [["4","4s"],["6","6s"],["8","8s"],["10","10s"]]),
      number(t("outputs"), "outputsPerPrompt", 1, 4),
      number(t("concurrency"), "concurrency", 1, 6),
      select(t("video_model"), "videoModel", [["veo-3.1-lite","Veo 3.1 Lite"],["veo-3.1-fast","Veo 3.1 Fast"],["veo-3.1-quality","Veo 3.1 Quality"],["omni-flash","Omni Flash"]]),
      select(t("image_model"), "imageModel", [["nano-banana-2-lite","Nano Banana 2 Lite"],["nano-banana-pro","Nano Banana Pro"],["nano-banana-2","Nano Banana 2"]]),
      number(t("delay") + " min", "delayMinMs", 0, 60000, 500),
      number(t("delay") + " max", "delayMaxMs", 0, 60000, 500),
      number(t("retries"), "retries", 0, 20),
      select(t("resolution") + " 🎬", "videoResolution", [["720p","720p"],["1080p","1080p"],["4k","4K"],["gif","GIF"]]),
      select(t("resolution") + " 🖼", "imageResolution", [["1k","1K"],["2k","2K"],["4k","4K"]]),
      select(t("language"), "language", i18n.languages.map((l) => [l, l.toUpperCase()])),
      toggle(t("auto_download"), "autoDownload"),
      toggle("Subcarpeta por proyecto", "subfolderByProject")
    );
    wrap.appendChild(grid);
    return wrap;
  }

  function buildLog() {
    return $("div", { id: "afs-log", className: "afs-log" });
  }

  // ----- Handlers ---------------------------------------------------------
  function collectPrompts() {
    const ta = root.querySelector("#afs-prompts");
    return prompts.parsePrompts(ta.value);
  }

  function onAddToQueue() {
    const list = collectPrompts();
    if (!list.length) { log("No hay prompts para agregar."); return; }
    const copies = Math.max(1, Number(settings.outputsPerPrompt) || 1);
    list.forEach((p) => {
      for (let i = 0; i < copies; i++) staged.push({ prompt: p, meta: { mode: settings.mode } });
    });
    log(`Agregados ${list.length * copies} jobs a la cola (modo ${settings.mode}).`);
    renderStaged();
  }

  async function onImportFile(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const text = await file.text();
    let list = [];
    if (/\.(csv|tsv)$/i.test(file.name)) {
      const rows = csv.parse(text);
      list = csv.columnToPrompts(rows, { hasHeader: rows.length > 1, column: 0 });
    } else {
      list = prompts.parsePrompts(text);
      if (list.length <= 1) list = prompts.parseLines(text); // txt de una linea por prompt
    }
    const ta = root.querySelector("#afs-prompts");
    ta.value = prompts.joinPrompts(list);
    log(`Importados ${list.length} prompts desde ${file.name}.`);
    e.target.value = "";
  }

  function makeAdapter() {
    return new FlowAdapter(settings, { download, log });
  }

  async function onStart() {
    if (engine && engine._running) { log("Ya esta corriendo."); return; }
    if (!staged.length) { log("La cola esta vacia. Agrega prompts primero."); return; }
    const adapter = makeAdapter();
    if (!adapter.onFlowProject()) { log(t("not_on_flow")); return; }

    engine = new QueueEngine({
      processJob: (job, ctx) => adapter.processJob(job, ctx),
      concurrency: Number(settings.concurrency) || 1,
      retries: Number(settings.retries) || 0,
      delayMs: [Number(settings.delayMinMs) || 0, Number(settings.delayMaxMs) || 0],
      onEvent: onEngineEvent,
    });
    engine.add(staged.map((j) => Object.assign({}, j)));
    staged = [];
    log(`Iniciando ${engine.jobs.length} jobs...`);
    renderQueue();
    await engine.start();
    log("Lote terminado.");
  }

  function onPauseResume() {
    if (!engine || !engine._running) return;
    const btn = root.querySelector("#afs-pause");
    if (engine._paused) { engine.resume(); btn.textContent = "⏸ " + t("pause"); }
    else { engine.pause(); btn.textContent = "▶ " + t("resume"); }
  }

  function onStop() { if (engine) engine.stop(); }
  function onClear() {
    staged = [];
    if (engine && !engine._running) engine.clear();
    renderQueue();
    log("Cola limpiada.");
  }

  function onEngineEvent(evt) {
    if (evt.type === "delay" && evt.job) log(`Esperando ${evt.job.waitMs || evt.waitMs}ms antes del siguiente...`);
    if (evt.type === "retry") log(`Reintentando job (intento ${evt.job.attempts}): ${evt.job.error}`);
    renderQueue(evt.counts);
  }

  // ----- Render de la cola ------------------------------------------------
  const STATUS_LABEL = {
    queued: () => t("status_queued"), generating: () => t("status_generating"),
    downloading: () => t("status_downloading"), completed: () => t("status_completed"),
    failed: () => t("status_failed"), skipped: () => t("status_skipped"),
  };

  function renderStaged() {
    const box = root.querySelector("#afs-queue");
    if (engine && engine._running) return; // no pisar la vista en vivo
    box.innerHTML = "";
    if (!staged.length) { box.appendChild($("div", { className: "afs-empty", textContent: t("empty_queue") })); return; }
    staged.forEach((j, i) => {
      const item = $("div", { className: "afs-item" }, [
        $("span", { className: "afs-chip afs-queued", textContent: t("status_queued") }),
        $("span", { className: "afs-item-text", textContent: j.prompt }),
        (() => { const b = $("button", { className: "afs-x", textContent: "✕" }); b.onclick = () => { staged.splice(i, 1); renderStaged(); }; return b; })(),
      ]);
      box.appendChild(item);
    });
    updateCounts({ total: staged.length, queued: staged.length });
  }

  function renderQueue(counts) {
    const box = root.querySelector("#afs-queue");
    if (!engine) return renderStaged();
    box.innerHTML = "";
    if (!engine.jobs.length) { box.appendChild($("div", { className: "afs-empty", textContent: t("empty_queue") })); return; }
    engine.jobs.forEach((j) => {
      const item = $("div", { className: "afs-item" }, [
        $("span", { className: "afs-chip afs-" + j.status, textContent: (STATUS_LABEL[j.status] || (() => j.status))() }),
        $("span", { className: "afs-item-text", textContent: j.prompt }),
        j.attempts > 1 ? $("span", { className: "afs-attempts", textContent: "×" + j.attempts }) : $("span"),
      ]);
      box.appendChild(item);
    });
    updateCounts(counts || engine.counts);
  }

  function updateCounts(c) {
    const el = root.querySelector("#afs-counts");
    if (!el || !c) return;
    el.textContent = `${c.completed || 0}/${c.total || 0} ✓  ${c.failed || 0} ✗`;
  }

  // ----- Tema / tamaño / arrastre ----------------------------------------
  function applyTheme() {
    root.classList.toggle("afs-theme-dark", settings.theme === "dark");
    root.classList.toggle("afs-theme-light", settings.theme === "light");
  }
  function toggleTheme() { settings.theme = settings.theme === "dark" ? "light" : "dark"; store.saveSettings({ theme: settings.theme }); applyTheme(); }
  function applySize() { root.classList.remove("afs-size-small", "afs-size-medium", "afs-size-large"); root.classList.add("afs-size-" + settings.panelSize); }
  function cycleSize() { const order = ["small", "medium", "large"]; settings.panelSize = order[(order.indexOf(settings.panelSize) + 1) % 3]; store.saveSettings({ panelSize: settings.panelSize }); applySize(); }

  function enableDrag(handle) {
    let sx, sy, ox, oy, dragging = false;
    handle.addEventListener("mousedown", (e) => {
      if (e.target.closest(".afs-icon-btn")) return;
      dragging = true; sx = e.clientX; sy = e.clientY;
      const r = root.getBoundingClientRect(); ox = r.left; oy = r.top;
      document.body.style.userSelect = "none";
    });
    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      root.style.left = Math.max(0, ox + e.clientX - sx) + "px";
      root.style.top = Math.max(0, oy + e.clientY - sy) + "px";
      root.style.right = "auto";
    });
    window.addEventListener("mouseup", () => { dragging = false; document.body.style.userSelect = ""; });
  }

  // ----- Montaje ----------------------------------------------------------
  async function mount() {
    settings = await store.getSettings();
    t = i18n.createTranslator(settings.language);

    const header = buildHeader();
    root.append(
      header,
      $("div", { className: "afs-body" }, [
        buildTabs(),
        buildComposer(),
        buildControls(),
        buildSettings(),
        buildQueue(),
        buildLog(),
      ])
    );
    document.documentElement.appendChild(root);
    applyTheme();
    applySize();
    enableDrag(header);
    renderStaged();
    log("AutoFlow Studio listo. " + (new FlowAdapter(settings, {}).onFlowProject() ? "Detectado proyecto de Flow ✓" : t("not_on_flow")));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
