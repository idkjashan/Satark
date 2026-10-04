#!/usr/bin/env node
// Generates the manifest's PNG icons from a plain shield silhouette - no image/canvas library,
// just a hand-rolled PNG encoder over Node's built-in zlib (deflate + crc32). "hand-craft simple
// PNGs" per the brief: this is a flat-colour shield, not a faithful render of src/components/Shield.tsx.
import { writeFileSync, mkdirSync } from 'node:fs';
import { deflateSync, crc32 } from 'node:zlib';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const TEAL = [15, 110, 140, 255];
const WHITE = [255, 255, 255, 255];
const TRANSPARENT = [0, 0, 0, 0];

// A shield outline in a 0-100 unit square, flat top and a pointed bottom.
const SHIELD = [
  [15, 10],
  [85, 10],
  [88, 46],
  [50, 94],
  [12, 46],
];

function scalePoly(poly, scale, cx = 50, cy = 50) {
  return poly.map(([x, y]) => [cx + (x - cx) * scale, cy + (y - cy) * scale]);
}

function pointInPolygon(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function chunk(type, data) {
  const typeBuf = Buffer.from(type, 'ascii');
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])) >>> 0);
  return Buffer.concat([len, typeBuf, data, crc]);
}

function encodePng(width, height, rgba) {
  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const ihdrData = Buffer.alloc(13);
  ihdrData.writeUInt32BE(width, 0);
  ihdrData.writeUInt32BE(height, 4);
  ihdrData[8] = 8; // bit depth
  ihdrData[9] = 6; // colour type: RGBA
  const stride = width * 4;
  const raw = Buffer.alloc((stride + 1) * height);
  for (let y = 0; y < height; y++) {
    raw[y * (stride + 1)] = 0; // filter: none
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, y * stride + stride);
  }
  return Buffer.concat([signature, chunk('IHDR', ihdrData), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}

function renderIcon(size, { maskable }) {
  const bg = maskable ? TEAL : TRANSPARENT;
  const shieldColor = maskable ? WHITE : TEAL;
  // Maskable icons get cropped to a circle/squircle by the OS; keep the shape inside that
  // safe zone by shrinking it well below full bleed.
  const shield = scalePoly(SHIELD, maskable ? 0.55 : 0.85);
  const rgba = Buffer.alloc(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const u = ((x + 0.5) / size) * 100;
      const v = ((y + 0.5) / size) * 100;
      const color = pointInPolygon(u, v, shield) ? shieldColor : bg;
      const idx = (y * size + x) * 4;
      rgba[idx] = color[0];
      rgba[idx + 1] = color[1];
      rgba[idx + 2] = color[2];
      rgba[idx + 3] = color[3];
    }
  }
  return encodePng(size, size, rgba);
}

const outDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'public', 'icons');
mkdirSync(outDir, { recursive: true });

for (const size of [192, 512]) {
  writeFileSync(path.join(outDir, `icon-${size}.png`), renderIcon(size, { maskable: false }));
  writeFileSync(path.join(outDir, `icon-maskable-${size}.png`), renderIcon(size, { maskable: true }));
  console.log(`wrote icon-${size}.png and icon-maskable-${size}.png`);
}
