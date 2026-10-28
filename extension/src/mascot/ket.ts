/**
 * Ket, Marginalia's mascot, drawn to the user's brief (docs/design.md): one enormous, slightly
 * flattened mass of ivory fleece, a small charcoal head at its upper front edge, close-set
 * protruding eyes, sideways leaf-shaped ears and short legs with flared hooves, in a handmade
 * clay look lit from the upper left. 100×100 canvas, about 8% clear padding.
 *
 * Built back to front in the brief's order: concealed legs, fleece, visible legs, ears, head,
 * eyes, nostrils, then texture. Single source of truth for the panel (React maps the shapes)
 * and the packaged icons (scripts/generate-icons.ts renders `toSvg`). No imports, so Node can
 * run it.
 */

export const VIEW = 100;

export const COLORS = {
  fleece: '#E8E1CF',
  fleeceLight: '#F6F1E5',
  fleeceShadow: '#BDB5A2',
  charcoal: '#343532',
  charcoalLight: '#50514B',
  charcoalDeep: '#262724',
  rim: '#6E6F68', // a thin rim light, so charcoal edges read on a dark page
  black: '#111210',
  eyeWhite: '#F7F5ED',
  lid: '#94747E',
  mark: '#8E96B0',
  sweat: '#8FC3F2',
} as const;

export interface Gradient {
  cx: number;
  cy: number;
  r: number;
  stops: readonly (readonly [number, string])[];
}

/** Radial gradients in each shape's own box: broad light from the upper left. */
export const GRADIENTS = {
  fleece: {
    cx: 0.36,
    cy: 0.26,
    r: 0.82,
    stops: [
      [0, COLORS.fleeceLight],
      [0.5, COLORS.fleece],
      [1, COLORS.fleeceShadow],
    ],
  },
  head: {
    cx: 0.36,
    cy: 0.26,
    r: 0.85,
    stops: [
      [0, COLORS.charcoalLight],
      [0.55, COLORS.charcoal],
      [1, COLORS.charcoalDeep],
    ],
  },
  leg: {
    cx: 0.3,
    cy: 0.2,
    r: 1,
    stops: [
      [0, COLORS.charcoalLight],
      [1, COLORS.charcoalDeep],
    ],
  },
} as const satisfies Record<string, Gradient>;

export type GradientId = keyof typeof GRADIENTS;

/** Groups the panel animates separately. */
export type Part = 'shadow' | 'legs' | 'wool' | 'head' | 'marks';

export interface Shape {
  part: Part;
  d: string;
  /** A colour, or a gradient by name. */
  fill?: string | { gradient: GradientId };
  stroke?: string;
  width?: number;
  opacity?: number;
}

export type Face = 'awake' | 'blink' | 'happy' | 'thinking' | 'worried' | 'asleep' | 'surprised';

const n = (v: number) => String(Math.round(v * 100) / 100);

export const circle = (cx: number, cy: number, r: number) =>
  `M${n(cx - r)} ${n(cy)}a${n(r)} ${n(r)} 0 1 0 ${n(2 * r)} 0a${n(r)} ${n(r)} 0 1 0 ${n(-2 * r)} 0Z`;

export const ellipse = (cx: number, cy: number, rx: number, ry: number) =>
  `M${n(cx - rx)} ${n(cy)}a${n(rx)} ${n(ry)} 0 1 0 ${n(2 * rx)} 0a${n(rx)} ${n(ry)} 0 1 0 ${n(-2 * rx)} 0Z`;

/** A small, repeatable random sequence (mulberry32), so the fleece looks the same every time. */
function seeded(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * The fleece's edge: an ellipse made of many small arcs, each pushed out a little by its own
 * amount, so the outline is softly uneven, like matted wool, not cloud-shaped scallops.
 */
export function fleeceOutline(
  cx: number,
  cy: number,
  rx: number,
  ry: number,
  bumps: number,
  seed: number,
  grow = 0,
): string {
  const rand = seeded(seed);
  const pts = Array.from({ length: bumps }, (_, i) => {
    const a = (2 * Math.PI * i) / bumps;
    const k = 1 + (rand() - 0.5) * 0.035;
    return [cx + (rx + grow) * k * Math.cos(a), cy + (ry + grow) * k * Math.sin(a)] as const;
  });
  const first = pts[0] ?? [cx, cy];
  let d = `M${n(first[0])} ${n(first[1])}`;
  for (let i = 1; i <= bumps; i++) {
    const p = pts[i % bumps] ?? first;
    const q = pts[i - 1] ?? first;
    const chord = Math.hypot(p[0] - q[0], p[1] - q[1]);
    const r = (chord / 2) * (1.25 + rand() * 0.5);
    d += `A${n(r)} ${n(r)} 0 0 1 ${n(p[0])} ${n(p[1])}`;
  }
  return `${d}Z`;
}

/** The Born rule: the chance a measurement finds |0⟩. */
export function probabilityOfZero(theta: number): number {
  return Math.cos(theta / 2) ** 2;
}

/** Measures in the computational basis: 0 for |0⟩, 1 for |1⟩. */
export function measure(theta: number, random: () => number = Math.random): 0 | 1 {
  return random() < probabilityOfZero(theta) ? 0 : 1;
}

// B, the fleece's width, is 72: everything below follows the brief's proportions.
export const FLEECE = { cx: 55, cy: 50.5, rx: 36, ry: 29 } as const; // height 0.8B
const HEAD = { cx: 28, top: 33, bottom: 57 } as const; // 0.26B wide, 0.33B tall
const EYE_L = { x: 24.4, y: 39.6 };
const EYE_R = { x: 30.8, y: 39 }; // a touch higher: handmade, not mirrored
const EYE_R_SIZE = 2.6; // larger than the brief's 0.05B, so the eyes survive at 32 px
const PUPIL = 0.46;

/** A short slim leg ending in a small flared hoof with a flat bottom. */
function leg(x: number, top: number, bottom: number): string {
  return [
    `M${n(x - 1.9)} ${n(top)}`,
    `L${n(x - 1.9)} ${n(bottom - 3.2)}`,
    `C${n(x - 2.1)} ${n(bottom - 1.8)} ${n(x - 2.9)} ${n(bottom - 1.1)} ${n(x - 2.9)} ${n(bottom)}`,
    `L${n(x + 2.9)} ${n(bottom)}`,
    `C${n(x + 2.9)} ${n(bottom - 1.1)} ${n(x + 2.1)} ${n(bottom - 1.8)} ${n(x + 1.9)} ${n(bottom - 3.2)}`,
    `L${n(x + 1.9)} ${n(top)}Z`,
  ].join('');
}

function hoof(x: number, bottom: number): string {
  return `M${n(x - 2.9)} ${n(bottom - 1.2)}H${n(x + 2.9)}V${n(bottom)}H${n(x - 2.9)}Z`;
}

/** The head: an elongated oval, domed forehead, broad heavy muzzle, all one shape. */
const HEAD_PATH = [
  `M${n(HEAD.cx)} ${n(HEAD.top)}`,
  'C33.6 33 36.2 37 36.8 42',
  'C37.6 48 38.2 53.4 34.6 56.2',
  'C32 58.2 24 58.2 21.4 56.2',
  'C17.8 53.4 18.4 48 19.2 42',
  `C19.8 37 22.4 ${n(HEAD.top)} ${n(HEAD.cx)} ${n(HEAD.top)}Z`,
].join('');

/**
 * One eye: protruding (a soft shadow below it), warm white, a round black pupil looking
 * (dx, dy), and the thin dusty-mauve rim on the upper lid. `lid` 0..1 closes it from the top,
 * `lower` raises a lower lid (a squint that reads as content).
 */
function eye(
  p: { x: number; y: number },
  r: number,
  dx: number,
  dy: number,
  lid: number,
  lower = 0,
): Shape[] {
  const shapes: Shape[] = [
    {
      part: 'head',
      d: ellipse(p.x + 0.2, p.y + 0.8, r + 0.35, r + 0.2),
      fill: COLORS.black,
      opacity: 0.45,
    },
    { part: 'head', d: circle(p.x, p.y, r), fill: COLORS.eyeWhite },
    { part: 'head', d: circle(p.x + dx, p.y + dy, r * PUPIL), fill: COLORS.black },
    {
      part: 'head',
      d: circle(p.x + dx - 0.45, p.y + dy - 0.5, r * 0.15),
      fill: COLORS.eyeWhite,
      opacity: 0.9,
    },
  ];
  const lidY = p.y - r + 2 * r * lid;
  if (lid > 0)
    shapes.push({
      part: 'head',
      d: `M${n(p.x - r - 0.4)} ${n(lidY)}A${n(r + 0.4)} ${n(r + 0.4)} 0 0 1 ${n(p.x + r + 0.4)} ${n(lidY)}Z`,
      fill: COLORS.charcoal,
    });
  if (lower > 0) {
    const y = p.y + r - 2 * r * lower;
    shapes.push({
      part: 'head',
      d: `M${n(p.x - r - 0.4)} ${n(y)}A${n(r + 0.4)} ${n(r + 0.4)} 0 0 0 ${n(p.x + r + 0.4)} ${n(y)}Z`,
      fill: COLORS.charcoal,
    });
  }
  // The rim follows the upper lid's edge, wherever the lid is.
  const span = Math.sqrt(Math.max(0, r * r - (lidY - p.y) ** 2));
  shapes.push({
    part: 'head',
    d:
      lid > 0
        ? `M${n(p.x - span - 0.2)} ${n(lidY)}L${n(p.x + span + 0.2)} ${n(lidY)}`
        : `M${n(p.x - r * 0.95)} ${n(p.y - r * 0.25)}A${n(r)} ${n(r)} 0 0 1 ${n(p.x + r * 0.95)} ${n(p.y - r * 0.25)}`,
    stroke: COLORS.lid,
    width: 0.75,
  });
  return shapes;
}

function closedEye(p: { x: number; y: number }, r: number, smiling: boolean): Shape[] {
  return [
    {
      part: 'head',
      d: ellipse(p.x + 0.2, p.y + 0.8, r + 0.35, r + 0.2),
      fill: COLORS.black,
      opacity: 0.3,
    },
    { part: 'head', d: circle(p.x, p.y, r), fill: COLORS.charcoalLight },
    {
      part: 'head',
      d: smiling
        ? `M${n(p.x - r * 0.85)} ${n(p.y + 0.5)}Q${n(p.x)} ${n(p.y - r * 0.9)} ${n(p.x + r * 0.85)} ${n(p.y + 0.5)}`
        : `M${n(p.x - r * 0.85)} ${n(p.y)}Q${n(p.x)} ${n(p.y + r * 0.7)} ${n(p.x + r * 0.85)} ${n(p.y)}`,
      stroke: COLORS.lid,
      width: 0.9,
    },
  ];
}

function face(kind: Face, look: number): Shape[] {
  const dx = Math.max(-1, Math.min(1, look)) * 0.9;
  const r = EYE_R_SIZE;
  const nostrils: Shape[] = [
    { part: 'head', d: ellipse(25.6, 52.4, 0.95, 0.75), fill: COLORS.black },
    { part: 'head', d: ellipse(30.4, 52.4, 0.95, 0.75), fill: COLORS.black },
  ];
  const mouth = (d: string): Shape => ({
    part: 'head',
    d,
    stroke: COLORS.black,
    width: 0.65,
    opacity: 0.75,
  });
  const neutral = mouth('M26.2 55.1Q28 55.6 29.8 55.1');
  switch (kind) {
    case 'awake':
      return [
        ...eye(EYE_L, r, dx, 0.15, 0.22),
        ...eye(EYE_R, r, dx, 0.15, 0.22),
        ...nostrils,
        neutral,
      ];
    case 'blink':
      return [...closedEye(EYE_L, r, false), ...closedEye(EYE_R, r, false), ...nostrils, neutral];
    case 'happy':
      return [
        ...eye(EYE_L, r, dx, 0, 0.12, 0.3),
        ...eye(EYE_R, r, dx, 0, 0.12, 0.3),
        ...nostrils,
        mouth('M26 54.7Q28 56 30 54.7'),
      ];
    case 'thinking':
      return [
        ...eye(EYE_L, r, 0.55, -0.85, 0.1),
        ...eye(EYE_R, r, 0.55, -0.85, 0.1),
        ...nostrils,
        mouth('M26.4 55.2Q28.4 54.8 29.8 55.4'),
      ];
    case 'worried':
      return [
        ...eye(EYE_L, r + 0.2, dx, 0.3, 0, 0),
        ...eye(EYE_R, r + 0.2, dx, 0.3, 0, 0),
        ...nostrils,
        mouth('M26 55.4Q27 54.7 28 55.4T30 55.4'),
      ];
    case 'asleep':
      return [...closedEye(EYE_L, r, false), ...closedEye(EYE_R, r, false), ...nostrils, neutral];
    case 'surprised':
      return [
        ...eye(EYE_L, r + 0.5, 0, 0, 0),
        ...eye(EYE_R, r + 0.5, 0, 0, 0),
        ...nostrils,
        { part: 'head', d: ellipse(28, 55.4, 0.9, 1.1), fill: COLORS.black, opacity: 0.85 },
      ];
  }
}

function marks(kind: Face): Shape[] {
  switch (kind) {
    case 'asleep':
      return [
        { part: 'marks', d: 'M40 17h6l-6 7h6', stroke: COLORS.mark, width: 2 },
        { part: 'marks', d: 'M49 9h4.5l-4.5 5h4.5', stroke: COLORS.mark, width: 1.6 },
      ];
    case 'thinking':
      return [0, 1, 2].map((i) => ({
        part: 'marks' as const,
        d: circle(40 + i * 5.5, 25 - i * 3.5, 1.9),
        fill: COLORS.mark,
      }));
    case 'worried':
      return [{ part: 'marks', d: 'M15.5 31q3 4.8 0 6.8q-3 -2 0 -6.8Z', fill: COLORS.sweat }];
    default:
      return [];
  }
}

/** Curls across the fleece: small, irregular, finer than the body; darker low, lighter high. */
function tufts(): Shape[] {
  const rand = seeded(7);
  const out: Shape[] = [];
  for (let i = 0; i < 46; i++) {
    const a = rand() * 2 * Math.PI;
    const d = Math.sqrt(rand()) * 0.86;
    const x = FLEECE.cx + FLEECE.rx * d * Math.cos(a);
    const y = FLEECE.cy + FLEECE.ry * d * Math.sin(a);
    // Leave the head and its shadow clear.
    if (Math.hypot(x - HEAD.cx, y - 45) < 13) continue;
    const r = 1.2 + rand() * 1.2;
    const turn = rand() * Math.PI;
    const x1 = x + r * Math.cos(turn);
    const y1 = y + r * Math.sin(turn);
    const x2 = x - r * Math.cos(turn);
    const y2 = y - r * Math.sin(turn);
    const low = y > FLEECE.cy - 4;
    out.push({
      part: 'wool',
      d: `M${n(x1)} ${n(y1)}A${n(r)} ${n(r * 0.8)} 0 0 1 ${n(x2)} ${n(y2)}`,
      stroke: low ? COLORS.fleeceShadow : x < FLEECE.cx ? '#FFFFFF' : COLORS.fleeceShadow,
      width: 0.6,
      opacity: low ? 0.32 : 0.28,
    });
  }
  return out;
}

export interface KetPose {
  face: Face;
  /** Where the eyes look, -1 (left) to 1 (right). */
  look?: number;
  /** Small icons get the silhouette and face only: no curls, no fuzzy edge. */
  detail?: boolean;
}

const LEG_TOP = 70; // well inside the fleece, which hides the top
const LEG_BOTTOM = 87; // the belly hangs to about 77 here: about 0.14B shows
/** A front pair and a hind pair, each a near leg and a far one: four legs. */
export const LEGS = { near: [39.5, 67.5], far: [45, 73] } as const;

/** Ket in draw order, back to front. */
export function ket(pose: KetPose): Shape[] {
  const detail = pose.detail !== false;
  const { cx, cy, rx, ry } = FLEECE;
  return [
    ...(detail
      ? [
          {
            part: 'shadow' as const,
            d: ellipse(56.5, 88.3, 26, 2.4),
            fill: COLORS.black,
            opacity: 0.16,
          },
        ]
      : []),
    // 1. Four legs, all drawn before the fleece so it hangs over their tops. The far leg of
    // each pair sits a little to the right and higher, a shade darker: further away.
    ...LEGS.far.map((x): Shape => ({
      part: 'legs',
      d: leg(x, LEG_TOP, LEG_BOTTOM - 1.4),
      fill: COLORS.charcoalDeep,
    })),
    ...LEGS.far.map((x): Shape => ({
      part: 'legs',
      d: hoof(x, LEG_BOTTOM - 1.4),
      fill: COLORS.black,
      opacity: 0.6,
    })),
    ...LEGS.near.map((x): Shape => ({
      part: 'legs',
      d: leg(x, LEG_TOP, LEG_BOTTOM),
      fill: { gradient: 'leg' },
      stroke: COLORS.rim,
      width: 0.45,
    })),
    ...LEGS.near.map((x): Shape => ({
      part: 'legs',
      d: hoof(x, LEG_BOTTOM),
      fill: COLORS.charcoalDeep,
    })),
    // 2. The fleece: a soft shadow, a fuzzy edge, the mass, then its curls.
    {
      part: 'wool',
      d: fleeceOutline(cx + 1.2, cy + 1.6, rx, ry, 44, 3),
      fill: COLORS.fleeceShadow,
      opacity: 0.85,
    },
    ...(detail
      ? [
          {
            part: 'wool' as const,
            d: fleeceOutline(cx, cy, rx, ry, 52, 5, 0.9),
            fill: COLORS.fleece,
            opacity: 0.45,
          },
        ]
      : []),
    { part: 'wool', d: fleeceOutline(cx, cy, rx, ry, 44, 3), fill: { gradient: 'fleece' } },
    ...(detail ? tufts() : []),
    // The head's shadow on the wool.
    { part: 'wool', d: ellipse(32, 51, 9, 9.5), fill: COLORS.fleeceShadow, opacity: 0.45 },
    // 3. (The legs are under the fleece, above.)
    // 4. Ears: short, flat, leaf-shaped, out to the sides with a slight droop, a groove for the fold.
    {
      part: 'head',
      d: 'M19.8 39.4C16 37.9 11.6 39.6 10.2 43.5C11.9 46 16.6 45.6 20 42.7Z',
      fill: { gradient: 'leg' },
      stroke: COLORS.rim,
      width: 0.45,
    },
    {
      part: 'head',
      d: 'M18.8 40.7C16 40.6 13.2 41.9 11.7 43.5',
      stroke: COLORS.charcoalDeep,
      width: 0.8,
    },
    {
      part: 'head',
      d: 'M36.2 39.4C40 37.9 44.4 39.6 45.8 43.5C44.1 46 39.4 45.6 36 42.7Z',
      fill: { gradient: 'leg' },
      stroke: COLORS.rim,
      width: 0.45,
    },
    {
      part: 'head',
      d: 'M37.2 40.7C40 40.6 42.8 41.9 44.3 43.5',
      stroke: COLORS.charcoalDeep,
      width: 0.8,
    },
    // 5. The head, with the muzzle's volume in soft light.
    { part: 'head', d: HEAD_PATH, fill: { gradient: 'head' }, stroke: COLORS.rim, width: 0.45 },
    { part: 'head', d: ellipse(28, 51.8, 7.2, 4.2), fill: COLORS.charcoalLight, opacity: 0.3 },
    {
      part: 'head',
      d: 'M23.4 35.6Q26.4 33.8 30 34.4',
      stroke: COLORS.charcoalLight,
      width: 1.1,
      opacity: 0.6,
    },
    // 6 and 7. Eyes, nostrils, mouth.
    ...face(pose.face, pose.look ?? 0),
    ...(detail ? marks(pose.face) : []),
  ];
}

export const ICON_SIZES = [16, 32, 48, 128] as const;

/** The packaged icon: neutral, with every detail where there is room for it. */
export function iconArt(size: number): Shape[] {
  return ket({ face: 'awake', detail: size >= 48 });
}

/**
 * The part of the canvas an icon shows. At 16 and 32 px the whole sheep makes the face a dot,
 * so small icons close in on the head and the front of the fleece, where the eyes and
 * nostrils stay readable.
 */
export function iconBox(size: number): { x: number; y: number; size: number } {
  return size >= 48 ? { x: 0, y: 0, size: VIEW } : { x: 6, y: 24, size: 54 };
}

function fillOf(s: Shape): string {
  if (s.fill === undefined) return 'none';
  return typeof s.fill === 'string' ? s.fill : `url(#k-${s.fill.gradient})`;
}

/** The gradients `shapes` use, as SVG <radialGradient> markup. */
export function gradientDefs(shapes: readonly Shape[]): string {
  const used = new Set(
    shapes.flatMap((s) => (typeof s.fill === 'object' ? [s.fill.gradient] : [])),
  );
  return [...used]
    .map((id) => {
      const g: Gradient = GRADIENTS[id];
      const stops = g.stops
        .map(([o, c]) => `<stop offset="${String(o)}" stop-color="${c}"/>`)
        .join('');
      return `<radialGradient id="k-${id}" cx="${String(g.cx)}" cy="${String(g.cy)}" r="${String(g.r)}">${stops}</radialGradient>`;
    })
    .join('');
}

/** Standalone SVG markup for `shapes`: what the icon script rasterises. */
export function toSvg(
  shapes: readonly Shape[],
  size: number,
  box: { x: number; y: number; size: number } = { x: 0, y: 0, size: VIEW },
): string {
  const paths = shapes
    .map((s) => {
      const stroke =
        s.stroke === undefined
          ? ''
          : ` stroke="${s.stroke}" stroke-width="${String(s.width ?? 1)}"`;
      const opacity = s.opacity === undefined ? '' : ` opacity="${String(s.opacity)}"`;
      return `<path d="${s.d}" fill="${fillOf(s)}"${stroke}${opacity} stroke-linecap="round" stroke-linejoin="round"/>`;
    })
    .join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${String(box.x)} ${String(box.y)} ${String(box.size)} ${String(box.size)}" width="${String(size)}" height="${String(size)}"><defs>${gradientDefs(shapes)}</defs>${paths}</svg>`;
}
