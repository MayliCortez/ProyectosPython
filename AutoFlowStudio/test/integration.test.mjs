/*
 * integration.test.mjs — Prueba de integracion con jsdom (sin navegador).
 *
 * Carga los MISMOS scripts de la extension (lib/*.js + content/inject.js) en
 * un DOM que imita un proyecto de Google Flow, y verifica el flujo completo:
 *   - El panel se monta e inyecta la UI (5 modos, cola, etc.)
 *   - Importar/agregar prompts a la cola y quitarlos
 *   - El FlowAdapter escribe el prompt en el textarea de Flow, pulsa Generar,
 *     detecta el resultado y dispara la descarga con el nombre correcto
 *   - El adaptador NO usa el textarea del propio panel
 *   - El popup renderiza y refleja el estado
 *
 * Ejecuta:  node test/integration.test.mjs
 */
import { JSDOM } from "jsdom";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const FLOW_URL = "https://labs.google/fx/tools/flow/project/mock123";

let passed = 0, failed = 0;
function check(name, cond, detail) {
  if (cond) { passed++; console.log("  \x1b[32m✓\x1b[0m " + name); }
  else { failed++; console.log("  \x1b[31m✗\x1b[0m " + name + (detail ? "\n      " + detail : "")); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// --- Construye un entorno jsdom que imita Google Flow --------------------
function makeFlowEnv() {
  const mockBody = `
    <h1>Mock Google Flow</h1>
    <textarea class="flow-prompt" placeholder="Escribe tu prompt para generar un video"></textarea>
    <button class="flow-generate" aria-label="Generate video">Generar</button>
    <div id="results"></div>`;
  const dom = new JSDOM(`<!DOCTYPE html><html><head></head><body>${mockBody}</body></html>`, {
    url: FLOW_URL,
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const { window } = dom;

  // jsdom no calcula layout: forzamos rects no-cero para que isVisible() funcione.
  window.Element.prototype.getBoundingClientRect = function () {
    return { width: 120, height: 32, top: 10, left: 10, right: 130, bottom: 42, x: 10, y: 10 };
  };
  window.Element.prototype.scrollIntoView = function () {};
  window.HTMLElement.prototype.scrollIntoView = function () {};

  // Descargas capturadas por el chrome shim.
  const downloads = [];
  window.chrome = {
    runtime: {
      lastError: null,
      getManifest: () => JSON.parse(read("manifest.json")),
      sendMessage: (msg, cb) => {
        if (msg && msg.type === "afs-download") downloads.push(msg);
        if (typeof cb === "function") cb({ ok: true });
      },
    },
    storage: {
      local: (() => {
        const mem = {};
        return {
          get: (keys, cb) => {
            const out = {};
            (Array.isArray(keys) ? keys : [keys]).forEach((k) => (out[k] = mem[k]));
            cb(out);
          },
          set: (obj, cb) => { Object.assign(mem, obj); if (cb) cb(); },
        };
      })(),
    },
  };

  // Comportamiento de Flow: al pulsar "Generar", aparece un <video> tras 200ms.
  const btn = window.document.querySelector(".flow-generate");
  btn.addEventListener("click", () => {
    window.setTimeout(() => {
      const v = window.document.createElement("video");
      v.src = "data:video/mp4;base64,AAAAHGZ0eXBpc29t";
      v.setAttribute("data-generated", "1");
      window.document.getElementById("results").appendChild(v);
    }, 200);
  });

  // Carga los scripts de la extension en el contexto de la ventana.
  const files = [
    "lib/i18n.js", "lib/store.js", "lib/prompt-parser.js", "lib/csv-parser.js",
    "lib/queue-engine.js", "lib/flow-adapter.js", "content/inject.js",
  ];
  for (const f of files) window.eval(read(f));

  return { dom, window, downloads };
}

(async () => {
  console.log("\n1) Montaje del panel en un proyecto de Flow");
  const { window, downloads } = makeFlowEnv();
  const doc = window.document;
  await sleep(80); // deja que mount() (async) termine

  check("panel #afs-root inyectado", doc.querySelectorAll("#afs-root").length === 1);
  check("titulo del panel", (doc.querySelector(".afs-title") || {}).textContent?.includes("AutoFlow Studio"));
  const tabs = doc.querySelectorAll(".afs-tab").length;
  check("5 pestañas de modo", tabs === 5, "tabs: " + tabs);
  check("textarea de composicion presente", !!doc.querySelector("#afs-prompts"));
  check("expuso window.AFS con modulos", !!(window.AFS && window.AFS.QueueEngine && window.AFS.FlowAdapter));

  console.log("\n2) Agregar prompts a la cola");
  const ta = doc.querySelector("#afs-prompts");
  ta.value = "un gato astronauta\n\nuna ciudad flotante\n\nun bosque de cristal";
  doc.querySelector("#afs-root .afs-primary").click(); // Agregar a la cola
  await sleep(20);
  let items = doc.querySelectorAll("#afs-queue .afs-item").length;
  check("3 prompts en la cola", items === 3, "items: " + items);
  check("contador refleja total", (doc.querySelector("#afs-counts").textContent || "").includes("/3"));

  doc.querySelector("#afs-queue .afs-item .afs-x").click(); // quitar uno
  await sleep(20);
  items = doc.querySelectorAll("#afs-queue .afs-item").length;
  check("quitar item deja 2", items === 2, "items: " + items);

  console.log("\n3) Cambiar de modo (pestañas)");
  const imgTab = [...doc.querySelectorAll(".afs-tab")].find((b) => b.dataset.mode === "text_to_image");
  imgTab.click();
  await sleep(10);
  check("pestaña 'Texto a Imagen' activa", imgTab.classList.contains("afs-active"));

  console.log("\n4) FlowAdapter automatiza contra el DOM de Flow");
  const AFS = window.AFS;
  const settings = Object.assign({}, AFS.store.DEFAULTS, { mode: "text_to_video", autoDownload: true });
  const captured = [];
  const adapter = new AFS.FlowAdapter(settings, {
    download: async (url, opts) => { captured.push({ url, opts }); return { ok: true }; },
    log: () => {},
  });
  check("onFlowProject() true en URL de proyecto", adapter.onFlowProject() === true);

  const job = { prompt: "prueba adaptador", meta: { mode: "text_to_video" } };
  const res = await adapter.processJob(job, { setDownloading: () => {}, isStopped: () => false });
  check("escribio prompt en textarea de Flow", doc.querySelector(".flow-prompt").value === "prueba adaptador", doc.querySelector(".flow-prompt").value);
  check("aparecio un video generado", !!doc.querySelector('#results video[data-generated]'));
  check("processJob devolvio ok", res && res.ok === true, JSON.stringify(res));
  check("disparo 1 descarga con data-URL", captured.length === 1 && captured[0].url.startsWith("data:video/mp4"), JSON.stringify(captured));
  check("nombre con prefijo afs_ y .mp4", captured[0] && /afs_.*\.mp4$/.test(captured[0].opts.filename), captured[0] && captured[0].opts.filename);
  check("subcarpeta por proyecto en el nombre", captured[0] && captured[0].opts.filename.includes("AutoFlowStudio_mock123"), captured[0] && captured[0].opts.filename);

  console.log("\n5) El adaptador NO toca el textarea del propio panel");
  check("textarea del panel intacto", doc.querySelector("#afs-prompts").value.length > 0);

  console.log("\n6) Popup renderiza y refleja estado");
  await testPopup(check);

  console.log(`\n\x1b[1mIntegracion: ${passed} pasaron, ${failed} fallaron\x1b[0m\n`);
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  console.log("\x1b[31mERROR FATAL\x1b[0m " + (e && e.stack || e));
  process.exit(1);
});

// --- Prueba del popup en su propio jsdom ---------------------------------
async function testPopup(check) {
  const html = read("popup/popup.html");
  const dom = new JSDOM(html, { url: "chrome-extension://abc/popup/popup.html", runScripts: "outside-only", pretendToBeVisual: true });
  const { window } = dom;
  window.chrome = {
    runtime: { getManifest: () => JSON.parse(read("manifest.json")) },
    tabs: {
      query: async () => [{ id: 1, url: "https://labs.google/fx/tools/flow/project/xyz" }],
      update: () => {}, create: () => {},
    },
  };
  window.AFS = {};
  window.eval(read("lib/store.js"));
  window.eval(read("popup/popup.js"));
  window.document.dispatchEvent(new window.Event("DOMContentLoaded"));
  await sleep(40);
  const doc = window.document;
  check("popup: titulo AutoFlow Studio", (doc.querySelector(".p-title").textContent || "").includes("AutoFlow Studio"));
  check("popup: version 1.0.0", (doc.querySelector("#p-version").textContent || "").includes("1.0.0"));
  check("popup: detecta proyecto de Flow", doc.querySelector("#p-status").classList.contains("ok"), doc.querySelector("#p-status").textContent);
}
