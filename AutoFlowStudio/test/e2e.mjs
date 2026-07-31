/*
 * e2e.mjs — Prueba end-to-end con Playwright + Chromium real.
 *
 * Carga la extension de verdad, intercepta https://labs.google/... con una
 * pagina mock, y verifica:
 *   1) La extension carga (service worker activo, id disponible).
 *   2) El popup renderiza.
 *   3) El content script inyecta el panel en un "proyecto de Flow".
 *   4) La UI funciona: importar prompts, agregar a la cola, verlos listados.
 *   5) El FlowAdapter automatiza: escribe el prompt, pulsa Generar, detecta
 *      el resultado y extrae la URL para descargar.
 *
 * Ejecuta con display virtual:  xvfb-run -a node test/e2e.mjs
 */
import { chromium } from "playwright";
import fs from "fs";
import os from "os";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const EXT_PATH = path.resolve(__dirname, "..");
const CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";
const MOCK_HTML = fs.readFileSync(path.join(__dirname, "mock-flow.html"), "utf8");
const FLOW_URL = "https://labs.google/fx/tools/flow/project/mocktest123";

let passed = 0, failed = 0;
function check(name, cond, detail) {
  if (cond) { passed++; console.log("  \x1b[32m✓\x1b[0m " + name); }
  else { failed++; console.log("  \x1b[31m✗\x1b[0m " + name + (detail ? "\n      " + detail : "")); }
}

const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "afs-e2e-"));

const context = await chromium.launchPersistentContext(userDataDir, {
  headless: false,
  executablePath: fs.existsSync(CHROME) ? CHROME : undefined,
  args: [
    `--disable-extensions-except=${EXT_PATH}`,
    `--load-extension=${EXT_PATH}`,
    "--no-sandbox",
    "--no-first-run",
  ],
});

try {
  // Interceptar labs.google para servir el mock (así el content script inyecta de verdad).
  await context.route(/labs\.google\/.*/, (route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: MOCK_HTML })
  );

  console.log("\n1) Carga de la extension");
  // Esperar al service worker (background MV3).
  let [sw] = context.serviceWorkers();
  if (!sw) sw = await context.waitForEvent("serviceworker", { timeout: 15000 }).catch(() => null);
  check("service worker activo", !!sw, "no aparecio el service worker");
  const extId = sw ? new URL(sw.url()).host : null;
  check("extension id disponible", !!extId, "sin id");

  // Ping al background (verifica messaging + manifest version).
  if (sw) {
    const pong = await sw.evaluate(async () => {
      return await new Promise((res) =>
        chrome.runtime.sendMessage({ type: "afs-ping" }, (r) => res(r))
      );
    }).catch((e) => ({ error: String(e) }));
    check("background responde ping con version", pong && pong.ok && pong.version === "1.0.0", JSON.stringify(pong));
  }

  console.log("\n2) Popup");
  const popup = await context.newPage();
  await popup.goto(`chrome-extension://${extId}/popup/popup.html`);
  await popup.waitForSelector(".p-title", { timeout: 8000 });
  const popupTitle = await popup.textContent(".p-title");
  check("popup renderiza titulo", popupTitle.includes("AutoFlow Studio"), popupTitle);
  const ver = await popup.textContent("#p-version");
  check("popup muestra version", ver.includes("1.0.0"), ver);
  await popup.close();

  console.log("\n3) Inyeccion del panel en un proyecto de Flow");
  const page = await context.newPage();
  await page.goto(FLOW_URL, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#afs-root", { timeout: 10000 });
  check("panel #afs-root inyectado", await page.locator("#afs-root").count() === 1);
  check("titulo del panel visible", (await page.textContent(".afs-title")).includes("AutoFlow Studio"));
  const tabs = await page.locator(".afs-tab").count();
  check("5 pestañas de modo", tabs === 5, "encontradas: " + tabs);

  console.log("\n4) UI: agregar prompts a la cola");
  await page.fill("#afs-prompts", "un gato astronauta\n\nuna ciudad flotante\n\nun bosque de cristal");
  await page.click("#afs-root .afs-primary"); // "Agregar a la cola"
  await page.waitForSelector("#afs-queue .afs-item", { timeout: 5000 });
  const items = await page.locator("#afs-queue .afs-item").count();
  check("3 prompts en la cola", items === 3, "items: " + items);
  const counts = await page.textContent("#afs-counts");
  check("contador refleja total", counts.includes("/3"), counts);

  // Quitar uno con la X.
  await page.locator("#afs-queue .afs-item .afs-x").first().click();
  const itemsAfter = await page.locator("#afs-queue .afs-item").count();
  check("quitar item de la cola", itemsAfter === 2, "items: " + itemsAfter);

  console.log("\n5) FlowAdapter automatiza contra el mock");
  const result = await page.evaluate(async () => {
    const AFS = window.AFS;
    const settings = Object.assign({}, AFS.store.DEFAULTS, {
      mode: "text_to_video",
      autoDownload: true,
      selectorsOverride: { projectUrl: /.*/ }, // permitir el mock
    });
    const downloads = [];
    const adapter = new AFS.FlowAdapter(settings, {
      download: async (url, opts) => { downloads.push({ url, opts }); return { ok: true }; },
      log: () => {},
    });
    const job = { prompt: "prueba adaptador", meta: { mode: "text_to_video" } };
    const ctx = { setDownloading: () => {}, isStopped: () => false };
    const res = await adapter.processJob(job, ctx);
    return {
      res,
      promptTyped: document.querySelector(".flow-prompt").value,
      downloads,
      hasVideo: !!document.querySelector('#results video[data-generated]'),
    };
  });
  check("escribio el prompt en el textarea de Flow", result.promptTyped === "prueba adaptador", result.promptTyped);
  check("genero un resultado (video)", result.hasVideo === true);
  check("proceso completado ok", result.res && result.res.ok === true, JSON.stringify(result.res));
  check("disparo una descarga con URL", result.downloads.length === 1 && result.downloads[0].url.startsWith("data:video/mp4"), JSON.stringify(result.downloads));
  check("nombre de archivo con prefijo y .mp4", result.downloads[0] && /afs_.*\.mp4$/.test(result.downloads[0].opts.filename), result.downloads[0] && result.downloads[0].opts.filename);

  console.log("\n6) El adaptador NO usa su propio textarea del panel");
  const panelUntouched = await page.evaluate(() => document.querySelector("#afs-prompts").value.length > 0);
  check("textarea del panel intacto (no fue el target)", panelUntouched === true);

} catch (err) {
  failed++;
  console.log("  \x1b[31m✗ ERROR FATAL\x1b[0m " + (err && err.stack || err));
} finally {
  await context.close();
  fs.rmSync(userDataDir, { recursive: true, force: true });
  console.log(`\n\x1b[1mE2E: ${passed} pasaron, ${failed} fallaron\x1b[0m\n`);
  process.exit(failed ? 1 : 0);
}
