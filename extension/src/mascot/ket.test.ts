import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  FLEECE,
  ICON_SIZES,
  iconArt,
  iconBox,
  ket,
  measure,
  probabilityOfZero,
  toSvg,
  type Face,
} from './ket';

describe('measurement', () => {
  it('follows the Born rule', () => {
    expect(probabilityOfZero(0)).toBe(1);
    expect(probabilityOfZero(Math.PI)).toBeCloseTo(0);
    expect(probabilityOfZero(Math.PI / 2)).toBeCloseTo(0.5);
    expect(measure(Math.PI / 2, () => 0.49)).toBe(0);
    expect(measure(Math.PI / 2, () => 0.51)).toBe(1);
    expect(measure(0, () => 0.999)).toBe(0);
  });
});

describe('ket', () => {
  it('keeps the brief: fleece height about 0.8 of its width, inside the padding', () => {
    expect(FLEECE.ry / FLEECE.rx).toBeGreaterThanOrEqual(0.75);
    expect(FLEECE.ry / FLEECE.rx).toBeLessThanOrEqual(0.85);
    expect(FLEECE.cx + FLEECE.rx).toBeLessThanOrEqual(92);
  });

  it('has a face for every mood, and marks only where they mean something', () => {
    const faces: Face[] = ['awake', 'blink', 'happy', 'worried', 'thinking', 'asleep', 'surprised'];
    for (const face of faces) expect(ket({ face }).some((s) => s.part === 'head')).toBe(true);
    expect(ket({ face: 'asleep' }).some((s) => s.part === 'marks')).toBe(true);
    expect(ket({ face: 'awake' }).some((s) => s.part === 'marks')).toBe(false);
  });

  it('keeps each part together, so the panel can animate it as one group', () => {
    const parts = ket({ face: 'awake' }).map((s) => s.part);
    const runs = parts.filter((p, i) => p !== parts[i - 1]);
    expect(new Set(runs).size).toBe(runs.length);
  });

  it('looks the same every time', () => {
    expect(ket({ face: 'awake' })).toEqual(ket({ face: 'awake' }));
  });
});

describe('packaged icons', () => {
  it('are up to date with the art (run `npm run icons`)', () => {
    const hash = createHash('sha256')
      .update(ICON_SIZES.map((size) => toSvg(iconArt(size), size, iconBox(size))).join('\n'))
      .digest('hex');
    const saved = readFileSync(
      path.resolve(import.meta.dirname, '../../scripts/icons.hash'),
      'utf8',
    );
    expect(saved.trim()).toBe(hash);
  });

  it('close in on the face and drop the curls where there is no room', () => {
    expect(iconBox(16).size).toBeLessThan(100);
    expect(iconBox(128).size).toBe(100);
    expect(iconArt(16).length).toBeLessThan(iconArt(128).length);
  });
});
