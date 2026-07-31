/*
 * store.js — Configuracion por defecto + acceso a chrome.storage.
 * UMD: en node (tests) cae a un mock en memoria.
 */
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.AFS = Object.assign(root.AFS || {}, { store: mod });
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  /** Valores por defecto — reflejan las opciones de VEO Automation. */
  const DEFAULTS = {
    // General
    mode: "text_to_video", // text_to_video | frame_to_video | ingredients_to_video | text_to_image | image_to_image
    aspectRatio: "16:9", // 16:9 | 9:16 | 1:1 | 3:4 | 4:3
    outputsPerPrompt: 1, // 1..4
    concurrency: 1, // 1..6 (concat/agent = 1)
    duration: 8, // 4 | 6 | 8 | 10 (segundos, solo video)
    // Modelos
    videoModel: "veo-3.1-fast", // veo-3.1-lite | veo-3.1-fast | veo-3.1-quality | omni-flash
    imageModel: "nano-banana-2", // nano-banana-2-lite | nano-banana-pro | nano-banana-2
    // Delays / reintentos
    delayMinMs: 3000,
    delayMaxMs: 7000,
    retries: 3,
    // Descarga
    autoDownload: true,
    videoResolution: "1080p", // 720p | 1080p | 4k | gif
    imageResolution: "2k", // 1k | 2k | 4k
    subfolderByProject: true,
    filenamePrefix: "afs_",
    // UI
    theme: "dark", // dark | light
    panelSize: "medium", // small | medium | large
    language: "es",
    // Selectores de Flow (ajustables sin tocar codigo). Ver flow-adapter.js
    selectorsOverride: null,
  };

  const hasChrome =
    typeof chrome !== "undefined" && chrome.storage && chrome.storage.local;

  // Mock en memoria para entornos sin chrome (tests de node).
  const memory = {};

  function get(keys) {
    if (hasChrome) {
      return new Promise((resolve) => {
        chrome.storage.local.get(keys, (res) => resolve(res || {}));
      });
    }
    const out = {};
    (Array.isArray(keys) ? keys : Object.keys(keys || memory)).forEach((k) => {
      out[k] = k in memory ? memory[k] : undefined;
    });
    return Promise.resolve(out);
  }

  function set(obj) {
    if (hasChrome) {
      return new Promise((resolve) => chrome.storage.local.set(obj, resolve));
    }
    Object.assign(memory, obj);
    return Promise.resolve();
  }

  /** Devuelve la config completa combinada con los defaults. */
  async function getSettings() {
    const stored = await get(["settings"]);
    return Object.assign({}, DEFAULTS, stored.settings || {});
  }

  /** Guarda un parche parcial de configuracion. */
  async function saveSettings(patch) {
    const current = await getSettings();
    const merged = Object.assign({}, current, patch);
    await set({ settings: merged });
    return merged;
  }

  async function resetSettings() {
    await set({ settings: Object.assign({}, DEFAULTS) });
    return Object.assign({}, DEFAULTS);
  }

  return { DEFAULTS, getSettings, saveSettings, resetSettings, _raw: { get, set } };
});
