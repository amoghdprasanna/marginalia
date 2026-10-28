/**
 * Writes the packaged icons (public/icon/<size>.png) from Ket's shapes in
 * src/mascot/ket.ts, and scripts/icons.hash so a unit test can tell when the
 * PNGs are out of date. Renders the same SVG the panel draws, in headless
 * Chromium. Run `npm run icons` after changing the art.
 */
import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { chromium } from '@playwright/test';
import { ICON_SIZES, iconArt, iconBox, toSvg } from '../src/mascot/ket.ts';

const outDir = path.resolve(import.meta.dirname, '../public/icon');
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage();
const svgs = ICON_SIZES.map((size) => toSvg(iconArt(size), size, iconBox(size)));
for (const [i, size] of ICON_SIZES.entries()) {
  const svg = svgs[i] ?? '';
  await page.setContent(`<body style="margin:0;background:transparent">${svg}</body>`);
  const file = path.join(outDir, `${String(size)}.png`);
  await page.locator('svg').screenshot({ path: file, omitBackground: true });
  console.log(`wrote ${path.relative(process.cwd(), file)}`);
}
await browser.close();

const hash = createHash('sha256').update(svgs.join('\n')).digest('hex');
writeFileSync(path.resolve(import.meta.dirname, 'icons.hash'), `${hash}\n`);
