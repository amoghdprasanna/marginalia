import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  BELL,
  COLORS,
  ICON_SIZES,
  iconArt,
  ket,
  measure,
  needle,
  probabilityOfZero,
  toSvg,
  type Face,
} from './ket';

describe('the bell needle', () => {
  it('points up for |0⟩ and down for |1⟩', () => {
    expect(needle(0).x).toBeCloseTo(BELL.cx);
    expect(needle(0).y).toBeLessThan(BELL.cy);
    expect(needle(Math.PI).y).toBeGreaterThan(BELL.cy);
  });
});

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
  it('has a face for every mood, and marks only where they mean something', () => {
    const faces: Face[] = ['awake', 'blink', 'happy', 'worried', 'thinking', 'asleep', 'surprised'];
    for (const face of faces) expect(ket({ face }).some((s) => s.part === 'face')).toBe(true);
    expect(ket({ face: 'asleep' }).some((s) => s.part === 'marks')).toBe(true);
    expect(ket({ face: 'awake' }).some((s) => s.part === 'marks')).toBe(false);
  });

  it('turns the needle red only on alarm', () => {
    const dot = (alarm: boolean) =>
      ket({ face: 'worried', alarm }).find((s) => s.part === 'needle' && s.fill !== undefined)
        ?.fill;
    expect(dot(true)).toBe('#F2735F');
    expect(dot(false)).toBe(COLORS.ink);
  });

  it('keeps each part together, so the panel can animate it as one group', () => {
    const parts = ket({ face: 'awake' }).map((s) => s.part);
    const runs = parts.filter((p, i) => p !== parts[i - 1]);
    expect(new Set(runs).size).toBe(runs.length);
  });
});

describe('packaged icons', () => {
  it('are up to date with the art (run `npm run icons`)', () => {
    const hash = createHash('sha256')
      .update(ICON_SIZES.map((size) => toSvg(iconArt(size), size)).join('\n'))
      .digest('hex');
    const saved = readFileSync(
      path.resolve(import.meta.dirname, '../../scripts/icons.hash'),
      'utf8',
    );
    expect(saved.trim()).toBe(hash);
  });

  it('drop the small details where there is no room', () => {
    expect(iconArt(16).some((s) => s.part === 'legs')).toBe(false);
    expect(iconArt(128).some((s) => s.part === 'legs')).toBe(true);
  });
});
