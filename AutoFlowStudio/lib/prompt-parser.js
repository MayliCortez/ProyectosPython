/*
 * prompt-parser.js — Convierte texto crudo en una lista de prompts.
 * UMD: funciona como content script (classic) y como modulo CommonJS en tests.
 *
 * Regla principal (igual que VEO Automation): los prompts se separan por
 * una LINEA EN BLANCO. Cada bloque = 1 prompt. Tambien acepta numeracion
 * ("1. ", "2) ") al inicio de linea, que se limpia.
 */
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.AFS = Object.assign(root.AFS || {}, { prompts: mod });
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  /** Quita numeracion tipo "12. ", "3) ", "- " del inicio de una linea. */
  function stripLeadingMarker(line) {
    return line.replace(/^\s*(?:\d+[.)]\s+|[-*•]\s+)/, "");
  }

  /**
   * Divide texto en prompts separados por lineas en blanco.
   * @param {string} raw
   * @returns {string[]} lista de prompts no vacios (recortados)
   */
  function parsePrompts(raw) {
    if (!raw || typeof raw !== "string") return [];
    // Normaliza saltos de linea y separa por 1+ lineas en blanco.
    const normalized = raw.replace(/\r\n?/g, "\n");
    return normalized
      .split(/\n[ \t]*\n+/)
      .map((block) =>
        block
          .split("\n")
          .map(stripLeadingMarker)
          .join("\n")
          .trim()
      )
      .filter((p) => p.length > 0);
  }

  /**
   * Variante "una linea = un prompt" (para importaciones simples).
   * @param {string} raw
   * @returns {string[]}
   */
  function parseLines(raw) {
    if (!raw || typeof raw !== "string") return [];
    return raw
      .replace(/\r\n?/g, "\n")
      .split("\n")
      .map((l) => stripLeadingMarker(l).trim())
      .filter((l) => l.length > 0);
  }

  /** Une una lista de prompts al formato editable (bloques con linea en blanco). */
  function joinPrompts(list) {
    return (list || []).map((p) => String(p).trim()).filter(Boolean).join("\n\n");
  }

  return { parsePrompts, parseLines, joinPrompts, stripLeadingMarker };
});
