/* popup.js — logica del popup de la barra del navegador. */
"use strict";

const FLOW_URL = "https://labs.google/fx/tools/flow";
const store = (self.AFS && self.AFS.store) || null;

async function init() {
  // Version
  const v = chrome.runtime.getManifest().version;
  document.getElementById("p-version").textContent = "v" + v;

  // Estado de la pestaña activa
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const status = document.getElementById("p-status");
  const onFlow = tab && /labs\.google\/fx\/.*tools\/flow\/project\//.test(tab.url || "");
  const onFlowHome = tab && /labs\.google\/fx\/.*tools\/flow/.test(tab.url || "");
  if (onFlow) {
    status.textContent = "✓ Proyecto de Flow detectado. El panel ⚡ está activo.";
    status.classList.add("ok");
  } else if (onFlowHome) {
    status.textContent = "Estás en Flow. Abre o crea un proyecto para ver el panel.";
  } else {
    status.textContent = "No estás en Google Flow. Pulsa el botón para abrirlo.";
  }

  // Ajustes rapidos
  if (store) {
    const s = await store.getSettings();
    document.getElementById("p-mode").value = s.mode;
    document.getElementById("p-autodl").checked = !!s.autoDownload;
    document.getElementById("p-mode").addEventListener("change", (e) =>
      store.saveSettings({ mode: e.target.value })
    );
    document.getElementById("p-autodl").addEventListener("change", (e) =>
      store.saveSettings({ autoDownload: e.target.checked })
    );
  }

  document.getElementById("p-open").addEventListener("click", async () => {
    if (onFlowHome && tab) {
      chrome.tabs.update(tab.id, { active: true });
    } else {
      chrome.tabs.create({ url: FLOW_URL });
    }
    window.close();
  });
}

document.addEventListener("DOMContentLoaded", init);
