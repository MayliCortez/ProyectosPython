/*
 * service-worker.js — Background MV3 de AutoFlow Studio.
 * Responsabilidades:
 *   - Descargar los resultados (chrome.downloads) con nombre/subcarpeta.
 *   - Puente opcional de "click confiable" via chrome.debugger para casos
 *     donde React ignora eventos sinteticos.
 *   - Abrir Google Flow cuando se hace clic en el icono si no hay pestaña.
 */

"use strict";

// Sanea un nombre de archivo/carpeta para chrome.downloads.
function sanitize(name) {
  return String(name || "output")
    .replace(/[<>:"\\|?*\u0000-\u001F]/g, "")
    .replace(/\.{2,}/g, ".")
    .replace(/^\/+|\/+$/g, "")
    .slice(0, 180);
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || typeof msg !== "object") return;

  if (msg.type === "afs-download") {
    const opts = msg.options || {};
    const filename = sanitize(opts.filename || "autoflow_output");
    chrome.downloads.download(
      { url: msg.url, filename, saveAs: false, conflictAction: "uniquify" },
      (downloadId) => {
        if (chrome.runtime.lastError) {
          sendResponse({ ok: false, error: chrome.runtime.lastError.message });
        } else {
          sendResponse({ ok: true, downloadId });
        }
      }
    );
    return true; // respuesta asincrona
  }

  if (msg.type === "afs-debugger-click" && sender.tab) {
    trustedClick(sender.tab.id, msg.x, msg.y)
      .then(() => sendResponse({ ok: true }))
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }

  if (msg.type === "afs-ping") {
    sendResponse({ ok: true, version: chrome.runtime.getManifest().version });
    return false;
  }
});

/**
 * Click "confiable" (isTrusted=true) via Chrome DevTools Protocol.
 * Se usa solo cuando el click sintetico del content script no basta.
 */
async function trustedClick(tabId, x, y) {
  const target = { tabId };
  await new Promise((res, rej) =>
    chrome.debugger.attach(target, "1.3", () =>
      chrome.runtime.lastError ? rej(chrome.runtime.lastError) : res()
    )
  );
  try {
    const press = (type) =>
      new Promise((res, rej) =>
        chrome.debugger.sendCommand(
          target,
          "Input.dispatchMouseEvent",
          { type, x, y, button: "left", clickCount: 1 },
          () => (chrome.runtime.lastError ? rej(chrome.runtime.lastError) : res())
        )
      );
    await press("mousePressed");
    await press("mouseReleased");
  } finally {
    await new Promise((res) => chrome.debugger.detach(target, res));
  }
}

// Al instalar, deja constancia en el log del SW.
chrome.runtime.onInstalled.addListener(() => {
  console.log("AutoFlow Studio instalado:", chrome.runtime.getManifest().version);
});
