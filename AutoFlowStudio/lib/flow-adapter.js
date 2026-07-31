/*
 * flow-adapter.js — Capa de automatizacion de Google Flow.
 *
 * Aqui viven los SELECTORES y las acciones concretas sobre el DOM de Flow
 * (labs.google/fx/tools/flow/project/...). Como el HTML de Flow cambia entre
 * versiones y esta ofuscado, NO usamos selectores fragiles: buscamos por
 * texto visible, aria-label, placeholder o data-testid con varias estrategias.
 *
 * >>> AJUSTE EN VIVO <<<
 * Si Google cambia la interfaz, edita el objeto SELECTORS (o pasa un override
 * desde Ajustes -> selectorsOverride). No hay que tocar el resto del codigo.
 *
 * UMD (content + node tests: en node solo se prueban los helpers puros).
 */
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.AFS = Object.assign(root.AFS || {}, { FlowAdapter: mod.FlowAdapter, flowHelpers: mod.helpers });
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // ----- Configuracion de selectores (editable) --------------------------
  const SELECTORS = {
    projectUrl: /labs\.google\/fx\/.*tools\/flow\/project\//,
    // Textarea principal del prompt. Estrategias en orden de preferencia.
    promptInput: {
      testId: ["prompt-input", "textarea"],
      placeholder: [/genera/i, /prompt/i, /describe/i, /escribe/i, /idea/i],
      css: ["textarea", 'div[contenteditable="true"]'],
    },
    // Boton de generar / crear.
    generateButton: {
      testId: ["generate-button", "create-button"],
      text: [/^generar$/i, /^crear$/i, /^generate$/i, /^create$/i, /^run$/i],
      aria: [/generar/i, /generate/i, /create/i],
    },
    // Selector de modo (Text to Video, etc.) — menu desplegable.
    modeSwitcher: {
      text: [/text to video/i, /frame to video/i, /ingredients to video/i, /text to image/i, /image to image/i],
      aria: [/mode/i, /modo/i, /tool/i],
    },
    // Boton/menu de modelo.
    modelMenu: {
      text: [/veo/i, /nano banana/i, /imagen/i, /omni/i],
      aria: [/model/i, /modelo/i],
    },
    // Boton de descarga en un resultado.
    downloadButton: {
      aria: [/download/i, /descargar/i, /guardar/i],
      testId: ["download-button", "download"],
    },
    // Contenedor de un resultado terminado (para saber que ya genero).
    resultItem: {
      css: ["video", 'img[src^="blob:"]', 'img[src*="lh3.googleusercontent"]'],
      testId: ["result-item", "generation-result"],
    },
    // Señal de "Unusual Activity".
    unusualActivity: {
      text: [/unusual activity/i, /actividad inusual/i, /verify/i, /verifica/i],
    },
  };

  // ----- Helpers de DOM (puros donde se puede) ---------------------------
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const helpers = {
    /** Normaliza texto para comparaciones (trim + colapsa espacios). */
    norm(s) {
      return String(s || "").replace(/\s+/g, " ").trim();
    },
    /** ¿Alguna regex de la lista matchea el texto? */
    anyMatch(text, patterns) {
      const t = helpers.norm(text);
      return (patterns || []).some((re) => re.test(t));
    },
    /** ¿El elemento es visible e interactuable? */
    isVisible(el) {
      if (!el || !el.getBoundingClientRect) return false;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return false;
      const style = (el.ownerDocument.defaultView || window).getComputedStyle(el);
      return style.visibility !== "hidden" && style.display !== "none" && style.opacity !== "0";
    },
  };

  // Estas funciones tocan `document`, asi que solo corren en el navegador.
  // IMPORTANTE: excluimos el subarbol del propio panel (#afs-root) para no
  // confundir nuestro textarea/botones con los de Google Flow.
  function notInPanel(el) {
    return el && !(el.closest && el.closest("#afs-root"));
  }
  function queryAll(sel) {
    return Array.prototype.slice.call(document.querySelectorAll(sel)).filter(notInPanel);
  }

  function findByTestId(ids) {
    for (const id of ids || []) {
      const el = queryAll(`[data-testid="${id}"], [data-test-id="${id}"]`).find(helpers.isVisible);
      if (el) return el;
    }
    return null;
  }

  function findByAria(patterns) {
    const nodes = queryAll("[aria-label]");
    return nodes.find((el) => helpers.isVisible(el) && helpers.anyMatch(el.getAttribute("aria-label"), patterns)) || null;
  }

  function findByText(patterns, tags) {
    const selector = (tags || ["button", "a", "[role=button]", "div", "span"]).join(",");
    const nodes = queryAll(selector);
    return (
      nodes.find(
        (el) => helpers.isVisible(el) && el.children.length <= 3 && helpers.anyMatch(el.textContent, patterns)
      ) || null
    );
  }

  function findByPlaceholder(patterns) {
    const nodes = queryAll("textarea, input, [contenteditable=true]");
    return (
      nodes.find(
        (el) => helpers.isVisible(el) && helpers.anyMatch(el.getAttribute("placeholder") || el.getAttribute("aria-label"), patterns)
      ) || null
    );
  }

  /** Busca un elemento probando testId -> aria -> text -> css. */
  function resolve(spec) {
    if (!spec) return null;
    let el = null;
    if (spec.testId) el = findByTestId(spec.testId);
    if (!el && spec.aria) el = findByAria(spec.aria);
    if (!el && spec.placeholder) el = findByPlaceholder(spec.placeholder);
    if (!el && spec.text) el = findByText(spec.text);
    if (!el && spec.css) {
      for (const css of spec.css) {
        const cand = queryAll(css).find(helpers.isVisible);
        if (cand) { el = cand; break; }
      }
    }
    return el;
  }

  async function waitFor(spec, timeoutMs, opts) {
    opts = opts || {};
    const deadline = Date.now() + (timeoutMs || 20000);
    while (Date.now() < deadline) {
      const el = resolve(spec);
      if (el) return el;
      if (opts.isStopped && opts.isStopped()) throw new Error("Detenido por el usuario");
      await sleep(400);
    }
    throw new Error("No se encontro el elemento (timeout): " + JSON.stringify(Object.keys(spec)));
  }

  /** Click "realista" que React acepta (secuencia completa de eventos). */
  function nativeClick(el) {
    if (!el) return false;
    el.scrollIntoView({ block: "center", behavior: "instant" });
    const rect = el.getBoundingClientRect();
    const opts = { bubbles: true, cancelable: true, view: window, clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 };
    for (const type of ["pointerover", "pointerenter", "pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
      const Ctor = type.startsWith("pointer") && window.PointerEvent ? PointerEvent : MouseEvent;
      el.dispatchEvent(new Ctor(type, opts));
    }
    return true;
  }

  /** Setea el valor de un input/textarea de forma que React lo detecte. */
  function setNativeValue(el, value) {
    if (!el) return false;
    if (el.getAttribute("contenteditable") === "true") {
      el.focus();
      el.textContent = value;
      el.dispatchEvent(new InputEvent("input", { bubbles: true, data: value, inputType: "insertText" }));
      return true;
    }
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    el.focus();
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  // ----- Adaptador -------------------------------------------------------
  class FlowAdapter {
    constructor(settings, api) {
      this.settings = settings || {};
      // api: { download(url, opts), log(msg) } — inyectado desde inject.js
      this.api = api || { download: async () => {}, log: () => {} };
      this.selectors = Object.assign({}, SELECTORS, (settings && settings.selectorsOverride) || {});
    }

    onFlowProject() {
      return this.selectors.projectUrl.test(location.href);
    }

    log(msg) { try { this.api.log(msg); } catch (e) {} }

    /** Punto de entrada usado por QueueEngine: procesa 1 job segun el modo. */
    async processJob(job, ctx) {
      if (!this.onFlowProject()) {
        throw new Error("No estas en un proyecto de Google Flow.");
      }
      await this._guardUnusualActivity();

      const mode = (job.meta && job.meta.mode) || this.settings.mode;
      this.log(`[${mode}] ${String(job.prompt).slice(0, 60)}...`);

      switch (mode) {
        case "text_to_video":
        case "frame_to_video":
        case "ingredients_to_video":
          return this._runVideoJob(job, ctx);
        case "text_to_image":
        case "image_to_image":
          return this._runImageJob(job, ctx);
        default:
          throw new Error("Modo no soportado: " + mode);
      }
    }

    async _guardUnusualActivity() {
      const el = resolve(this.selectors.unusualActivity);
      if (el) {
        // Enfriamiento proporcional antes de reintentar (como VEO Automation).
        this.log("Detectado 'Unusual Activity'. Enfriando 30s...");
        await sleep(30000);
        throw new Error("Unusual Activity — reintentando tras enfriamiento");
      }
    }

    async _typePrompt(job) {
      const input = await waitFor(this.selectors.promptInput, 20000);
      setNativeValue(input, job.prompt);
      await sleep(300);
      return input;
    }

    async _clickGenerate(ctx) {
      const btn = await waitFor(this.selectors.generateButton, 15000, ctx);
      nativeClick(btn);
    }

    /** Espera a que aparezca un resultado nuevo terminado. */
    async _waitForResult(ctx, timeoutMs) {
      const before = queryAll("video, img").length;
      const deadline = Date.now() + (timeoutMs || 300000); // hasta 5 min
      while (Date.now() < deadline) {
        if (ctx && ctx.isStopped && ctx.isStopped()) throw new Error("Detenido");
        await this._guardUnusualActivity();
        const item = resolve(this.selectors.resultItem);
        const now = queryAll("video, img").length;
        if (item && now > before) return item;
        await sleep(1500);
      }
      throw new Error("Timeout esperando el resultado de Flow");
    }

    async _runVideoJob(job, ctx) {
      await this._typePrompt(job);
      // TODO(live): seleccionar duracion/modelo desde el menu si aplica.
      await this._clickGenerate(ctx);
      const item = await this._waitForResult(ctx, 360000);
      if (this.settings.autoDownload) {
        ctx.setDownloading();
        await this._downloadResult(item, job, "mp4");
      }
      return { ok: true, type: "video" };
    }

    async _runImageJob(job, ctx) {
      await this._typePrompt(job);
      await this._clickGenerate(ctx);
      const item = await this._waitForResult(ctx, 180000);
      if (this.settings.autoDownload) {
        ctx.setDownloading();
        await this._downloadResult(item, job, "png");
      }
      return { ok: true, type: "image" };
    }

    /** Descarga el resultado: extrae la URL y delega en background (chrome.downloads). */
    async _downloadResult(item, job, ext) {
      let url = null;
      if (item.tagName === "VIDEO") url = item.currentSrc || item.src || (item.querySelector("source") || {}).src;
      else if (item.tagName === "IMG") url = item.currentSrc || item.src;
      if (!url) {
        // Fallback: clic en el boton de descarga del propio Flow.
        const dl = resolve(this.selectors.downloadButton);
        if (dl) { nativeClick(dl); return { via: "button" }; }
        throw new Error("No se pudo obtener la URL del resultado");
      }
      const safe = helpers.norm(job.prompt).slice(0, 40).replace(/[^\w\- ]+/g, "").replace(/\s+/g, "_");
      const prefix = this.settings.filenamePrefix || "afs_";
      const sub = this.settings.subfolderByProject ? this._projectName() + "/" : "";
      await this.api.download(url, { filename: `${sub}${prefix}${safe || "output"}.${ext}` });
      return { via: "url", url };
    }

    _projectName() {
      const m = location.href.match(/project\/([\w-]+)/);
      return "AutoFlowStudio_" + (m ? m[1].slice(0, 8) : "flow");
    }
  }

  FlowAdapter.SELECTORS = SELECTORS;
  return { FlowAdapter, helpers: Object.assign({ resolve, waitFor, nativeClick, setNativeValue, findByText, findByAria, findByPlaceholder }, helpers) };
});
