/**
 * Writes the packaged icons (public/icon/<size>.png) from Ket's shapes in
 * src/mascot/ket.ts, and scripts/icons.hash so a unit test can tell when the
 * PNGs are out of date. Rasterises in headless Chromium with the same paint()
 * the shapes are drawn with. Run `npm run icons` after changing the art.
 */
import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { chromium } from '@playwright/test';
import { ICON_SIZES, iconArt, paint } from '../src/mascot/ket.ts';

const outDir = path.resolve(import.meta.dirname, '../public/icon');
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage();
for (const size of ICON_SIZES) {
  const shapes = iconArt(size);
  const dataUrl = await page.evaluate(
    ({ paintSource, shapes, size }) => {
      // Our own paint(), sent as source: page.evaluate cannot take module imports.
      // eslint-disable-next-line @typescript-eslint/no-implied-eval
      const makePaint = new Function(`return ${paintSource}`) as () => typeof paint;
      const canvas = document.createElement('canvas');
      canvas.width = size;
      canvas.height = size;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('no 2D canvas');
      makePaint()(ctx, shapes, size, (d) => new Path2D(d));
      return canvas.toDataURL('image/png');
    },
    { paintSource: paint.toString(), shapes, size },
  );
  const file = path.join(outDir, `${String(size)}.png`);
  writeFileSync(file, Buffer.from(dataUrl.split(',')[1] ?? '', 'base64'));
  console.log(`wrote ${path.relative(process.cwd(), file)}`);
}
await browser.close();

writeFileSync(path.resolve(import.meta.dirname, 'icons.hash'), `${iconsHash()}\n`);

function iconsHash(): string {
  return createHash('sha256')
    .update(JSON.stringify(ICON_SIZES.map((size) => iconArt(size))))
    .digest('hex');
}
