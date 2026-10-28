import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  ARM,
  ICON_SIZES,
  iconArt,
  ket,
  measure,
  probabilityOfZero,
  project,
  SPHERE,
  TILT,
} from './ket';

const L = ARM * SPHERE.r;

describe('project', () => {
  it('puts |0⟩ straight up and |1⟩ straight down', () => {
    const up = project({ theta: 0, phi: 0 });
    expect(up.x).toBeCloseTo(SPHERE.cx);
    expect(up.y).toBeCloseTo(SPHERE.cy - L * Math.sqrt(1 - TILT ** 2));
    const down = project({ theta: Math.PI, phi: 0 });
    expect(down.y).toBeGreaterThan(SPHERE.cy);
  });

  it('draws the front half of the equator lower, like the desktop orb', () => {
    const front = project({ theta: Math.PI / 2, phi: Math.PI / 2 });
    const back = project({ theta: Math.PI / 2, phi: -Math.PI / 2 });
    expect(front.y).toBeCloseTo(SPHERE.cy + L * TILT);
    expect(front.behind).toBe(false);
    expect(back.behind).toBe(true);
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
  it('hides a vector pointing away behind the sphere', () => {
    const away = ket({ state: { theta: 1, phi: -Math.PI / 2 }, face: 'awake' });
    const toward = ket({ state: { theta: 1, phi: Math.PI / 2 }, face: 'awake' });
    expect(away[0]?.part).toBe('vector');
    expect(toward[0]?.part).toBe('body');
  });

  it('turns the dot red only on alarm', () => {
    const dot = (alarm: boolean) =>
      ket({ state: { theta: 0, phi: 0 }, face: 'worried', alarm }).find(
        (s) => s.part === 'vector' && s.fill !== undefined,
      )?.fill;
    expect(dot(true)).toBe('#F2735F');
    expect(dot(false)).toBe('#FFB224');
  });

  it('has a face for every mood', () => {
    for (const face of [
      'awake',
      'blink',
      'happy',
      'worried',
      'thinking',
      'asleep',
      'surprised',
    ] as const)
      expect(ket({ state: { theta: 0, phi: 0 }, face }).some((s) => s.part === 'face')).toBe(true);
  });
});

describe('packaged icons', () => {
  it('are up to date with the art (run `npm run icons`)', () => {
    const hash = createHash('sha256')
      .update(JSON.stringify(ICON_SIZES.map((size) => iconArt(size))))
      .digest('hex');
    const saved = readFileSync(
      path.resolve(import.meta.dirname, '../../scripts/icons.hash'),
      'utf8',
    );
    expect(saved.trim()).toBe(hash);
  });

  it('leave the face off where there is no room for it', () => {
    expect(iconArt(16).some((s) => s.part === 'face')).toBe(false);
    expect(iconArt(128).some((s) => s.part === 'face')).toBe(true);
  });
});
