/*
 * csv-parser.js — Parser CSV/TSV minimo sin dependencias.
 * Soporta comillas dobles, comas/tabs, saltos de linea dentro de celdas y
 * el escape "" dentro de campos entre comillas. UMD (content + node tests).
 *
 * Para .xlsx la extension usa SheetJS cargado aparte; aqui solo texto plano.
 */
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.AFS = Object.assign(root.AFS || {}, { csv: mod });
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  /**
   * Detecta el delimitador mas probable (coma, tab o punto y coma).
   * @param {string} sample
   */
  function detectDelimiter(sample) {
    const firstLine = (sample.split(/\r\n?|\n/)[0] || "");
    const counts = { ",": 0, "\t": 0, ";": 0 };
    let inQuotes = false;
    for (const ch of firstLine) {
      if (ch === '"') inQuotes = !inQuotes;
      else if (!inQuotes && ch in counts) counts[ch]++;
    }
    return Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0] || ",";
  }

  /**
   * Parsea CSV a matriz de filas (array de arrays de strings).
   * @param {string} text
   * @param {string} [delimiter] autodetectado si se omite
   * @returns {string[][]}
   */
  function parse(text, delimiter) {
    if (!text) return [];
    const delim = delimiter || detectDelimiter(text);
    const rows = [];
    let row = [];
    let field = "";
    let inQuotes = false;
    const src = String(text).replace(/\r\n?/g, "\n");

    for (let i = 0; i < src.length; i++) {
      const ch = src[i];
      if (inQuotes) {
        if (ch === '"') {
          if (src[i + 1] === '"') {
            field += '"';
            i++;
          } else {
            inQuotes = false;
          }
        } else {
          field += ch;
        }
      } else if (ch === '"') {
        inQuotes = true;
      } else if (ch === delim) {
        row.push(field);
        field = "";
      } else if (ch === "\n") {
        row.push(field);
        rows.push(row);
        row = [];
        field = "";
      } else {
        field += ch;
      }
    }
    // Ultimo campo/fila si el archivo no termina en salto de linea.
    if (field.length > 0 || row.length > 0) {
      row.push(field);
      rows.push(row);
    }
    return rows.filter((r) => r.some((c) => c.trim() !== ""));
  }

  /**
   * Extrae los prompts de una columna (por indice o por nombre de cabecera).
   * @param {string[][]} rows
   * @param {object} opts { hasHeader:boolean, column:number|string }
   * @returns {string[]}
   */
  function columnToPrompts(rows, opts) {
    opts = opts || {};
    if (!rows.length) return [];
    let header = null;
    let dataRows = rows;
    if (opts.hasHeader) {
      header = rows[0];
      dataRows = rows.slice(1);
    }
    let colIndex = 0;
    if (typeof opts.column === "number") {
      colIndex = opts.column;
    } else if (typeof opts.column === "string" && header) {
      const idx = header.findIndex(
        (h) => h.trim().toLowerCase() === opts.column.trim().toLowerCase()
      );
      colIndex = idx >= 0 ? idx : 0;
    }
    return dataRows.map((r) => (r[colIndex] || "").trim()).filter(Boolean);
  }

  return { parse, detectDelimiter, columnToPrompts };
});
