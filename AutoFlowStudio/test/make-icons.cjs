/* make-icons.cjs — Genera iconos PNG (16/48/128) sin dependencias.
   Dibuja un cuadrado redondeado con degradado teal y un rayo blanco. */
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

function crc32(buf) {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return (~c) >>> 0;
}
function chunk(type, data) {
  const t = Buffer.from(type, "ascii");
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([t, data])), 0);
  return Buffer.concat([len, t, data, crc]);
}
function png(size) {
  const bg = [0x16, 0xd1, 0xa1];
  const bg2 = [0x0f, 0x8f, 0x74];
  const white = [0xff, 0xff, 0xff];
  const r = size; // radio de esquina relativo
  const raw = Buffer.alloc(size * (size * 4 + 1));
  // Coordenadas del rayo (bolt) normalizadas.
  const bolt = [
    [0.56, 0.08], [0.30, 0.55], [0.47, 0.55], [0.40, 0.92],
    [0.72, 0.42], [0.53, 0.42], [0.62, 0.08],
  ].map(([x, y]) => [x * size, y * size]);
  function inPoly(px, py, poly) {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
      if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
  const corner = size * 0.18;
  for (let y = 0; y < size; y++) {
    let off = y * (size * 4 + 1);
    raw[off++] = 0; // filtro none
    for (let x = 0; x < size; x++) {
      // Esquinas redondeadas -> transparente.
      let a = 255;
      const cx = Math.min(x, size - 1 - x), cy = Math.min(y, size - 1 - y);
      if (cx < corner && cy < corner) {
        const dx = corner - cx, dy = corner - cy;
        if (Math.sqrt(dx * dx + dy * dy) > corner) a = 0;
      }
      let col;
      if (inPoly(x + 0.5, y + 0.5, bolt)) col = white;
      else {
        const tt = y / size;
        col = [
          Math.round(bg[0] * (1 - tt) + bg2[0] * tt),
          Math.round(bg[1] * (1 - tt) + bg2[1] * tt),
          Math.round(bg[2] * (1 - tt) + bg2[2] * tt),
        ];
      }
      raw[off++] = col[0];
      raw[off++] = col[1];
      raw[off++] = col[2];
      raw[off++] = a;
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // RGBA
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  return Buffer.concat([
    sig,
    chunk("IHDR", ihdr),
    chunk("IDAT", zlib.deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

const outDir = path.join(__dirname, "..", "icons");
fs.mkdirSync(outDir, { recursive: true });
for (const s of [16, 48, 128]) {
  fs.writeFileSync(path.join(outDir, `icon${s}.png`), png(s));
  console.log("icon" + s + ".png generado");
}
