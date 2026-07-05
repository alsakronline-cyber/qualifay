// Generate LeadList icons using pure Node.js (no canvas dependency)
// Creates minimal valid PNG files at 16, 48, 128 px

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

function createPNG(size) {
  // PNG signature
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

  function chunk(type, data) {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    const typeB = Buffer.from(type);
    const crcData = Buffer.concat([typeB, data]);
    const crc = crc32(crcData);
    const crcB = Buffer.alloc(4);
    crcB.writeUInt32BE(crc >>> 0);
    return Buffer.concat([len, typeB, data, crcB]);
  }

  // IHDR
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8;  // bit depth
  ihdr[9] = 2;  // color type RGB
  ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;

  // Draw pixel data (RGBA -> RGB)
  const pixels = [];
  const cx = size / 2, cy = size / 2;
  const pad = size * 0.08;

  for (let y = 0; y < size; y++) {
    pixels.push(0); // filter byte
    for (let x = 0; x < size; x++) {
      const color = getPixel(x, y, size, pad);
      pixels.push(color[0], color[1], color[2]);
    }
  }

  const raw = Buffer.from(pixels);
  const compressed = zlib.deflateSync(raw, { level: 9 });
  const idat = chunk('IDAT', compressed);
  const iend = chunk('IEND', Buffer.alloc(0));
  const ihdrC = chunk('IHDR', ihdr);

  return Buffer.concat([sig, ihdrC, idat, iend]);
}

function getPixel(x, y, size, pad) {
  const BG  = [15, 17, 23];    // #0f1117
  const BLUE = [13, 110, 253]; // #0D6EFD
  const WHITE = [255, 255, 255];

  // Rounded rect background
  const r = size * 0.2;
  const inRoundRect = inRoundedRect(x, y, 0, 0, size, size, r);
  if (!inRoundRect) return BG;

  // Draw gradient bg (blue)
  const gradR = Math.round(lerp(13, 30, y / size));
  const gradG = Math.round(lerp(110, 60, y / size));
  const gradB = Math.round(lerp(253, 180, y / size));

  // Three bars
  const barW = size * 0.18;
  const gap = size * 0.06;
  const totalW = 3 * barW + 2 * gap;
  const startX = (size - totalW) / 2;

  const bar1x = startX;
  const bar2x = startX + barW + gap;
  const bar3x = startX + 2 * (barW + gap);

  const bar1h = size * 0.35;
  const bar2h = size * 0.55;
  const bar3h = size * 0.75;

  const barBottom = size * 0.88;
  const barR = barW * 0.3;

  const inBar1 = inRoundedRect(x, y, bar1x, barBottom - bar1h, barW, bar1h, barR);
  const inBar2 = inRoundedRect(x, y, bar2x, barBottom - bar2h, barW, bar2h, barR);
  const inBar3 = inRoundedRect(x, y, bar3x, barBottom - bar3h, barW, bar3h, barR);

  if (inBar1 || inBar2 || inBar3) return WHITE;

  // Two dots
  const dotR = size * 0.07;
  const dot1x = bar1x + barW / 2;
  const dot1y = barBottom - bar1h - dotR * 1.5;
  const dot2x = bar3x + barW / 2;
  const dot2y = barBottom - bar3h - dotR * 1.5;

  if (dist(x, y, dot1x, dot1y) <= dotR) return WHITE;
  if (dist(x, y, dot2x, dot2y) <= dotR) return WHITE;

  return [gradR, gradG, gradB];
}

function inRoundedRect(px, py, x, y, w, h, r) {
  if (px < x || px > x + w || py < y || py > y + h) return false;
  if (px < x + r && py < y + r && dist(px, py, x + r, y + r) > r) return false;
  if (px > x + w - r && py < y + r && dist(px, py, x + w - r, y + r) > r) return false;
  if (px < x + r && py > y + h - r && dist(px, py, x + r, y + h - r) > r) return false;
  if (px > x + w - r && py > y + h - r && dist(px, py, x + w - r, y + h - r) > r) return false;
  return true;
}

function dist(x1, y1, x2, y2) {
  return Math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2);
}

function lerp(a, b, t) { return a + (b - a) * t; }

// CRC32
const crcTable = (() => {
  const t = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let j = 0; j < 8; j++) c = (c & 1) ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[i] = c;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = crcTable[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

// Output dir
const outDir = path.join(__dirname, 'icons');
if (!fs.existsSync(outDir)) fs.mkdirSync(outDir);

[16, 48, 128].forEach(size => {
  const png = createPNG(size);
  const file = path.join(outDir, `icon${size}.png`);
  fs.writeFileSync(file, png);
  console.log(`✓ Created ${file} (${png.length} bytes)`);
});

console.log('\n✅ All icons generated successfully!');
