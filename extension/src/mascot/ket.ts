/**
 * Ket, Marginalia's mascot: an original round, fluffy lamb with a soft, hand-made clay look,
 * on a 100×100 canvas. Its collar bell is a little Bloch sphere: the bell's needle is the
 * qubit's state, so a click "measures" it with the Born rule.
 *
 * Single source of truth for the panel (React maps the shapes) and the packaged icons
 * (scripts/generate-icons.ts renders `toSvg`). No imports, so Node can run it.
 */

export const VIEW = 100;

export const COLORS = {
  ink: '#1B2031',
  white: '#FFFFFF',
  woolShadow: '#CDBFA8',
  ear: '#F0B49C',
  earIn: '#F39C93',
  cheek: '#FF9C8F',
  tongue: '#F27C8C',
  amberDeep: '#D98A00',
  error: '#F2735F',
  mark: '#8E96B0',
  sweat: '#8FC3F2',
} as const;

export interface Gradient {
  cx: number;
  cy: number;
  r: number;
  stops: readonly (readonly [number, string])[];
}

/** Radial gradients in each shape's own box: light from the upper left, like clay under a lamp. */
export const GRADIENTS = {
  wool: {
    cx: 0.36,
    cy: 0.28,
    r: 0.8,
    stops: [
      [0, '#FFFFFF'],
      [0.55, '#F7F2E8'],
      [1, '#DCD1BF'],
    ],
  },
  puff: {
    cx: 0.35,
    cy: 0.3,
    r: 0.75,
    stops: [
      [0, '#FFFFFF'],
      [1, '#EEE6D8'],
    ],
  },
  face: {
    cx: 0.4,
    cy: 0.32,
    r: 0.8,
    stops: [
      [0, '#FFF1E6'],
      [1, '#F2C4AC'],
    ],
  },
  leg: {
    cx: 0.35,
    cy: 0.25,
    r: 0.9,
    stops: [
      [0, '#535A75'],
      [1, '#2A2F44'],
    ],
  },
  bell: {
    cx: 0.35,
    cy: 0.3,
    r: 0.8,
    stops: [
      [0, '#FFD77F'],
      [1, '#EB9A00'],
    ],
  },
} as const satisfies Record<string, Gradient>;

export type GradientId = keyof typeof GRADIENTS;

/** Groups the panel animates separately. */
export type Part = 'shadow' | 'legs' | 'wool' | 'ears' | 'face' | 'bell' | 'needle' | 'marks';

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

/**
 * A wool cloud: arcs bulging out of a circle. `wobble` varies each bump a little, so the
 * outline looks pinched by hand rather than drawn with a compass.
 */
export function cloud(
  cx: number,
  cy: number,
  r: number,
  bumps: number,
  rot = 0,
  wobble = 0,
): string {
  const pts = Array.from({ length: bumps }, (_, i) => {
    const a = rot + (2 * Math.PI * i) / bumps;
    const rr = r * (1 + wobble * Math.sin(i * 2.3 + 1));
    return [cx + rr * Math.cos(a), cy + rr * Math.sin(a)] as const;
  });
  const chord = 2 * r * Math.sin(Math.PI / bumps);
  const first = pts[0] ?? [cx, cy];
  let d = `M${n(first[0])} ${n(first[1])}`;
  for (let i = 1; i <= bumps; i++) {
    const p = pts[i % bumps] ?? first;
    const br = (chord / 2) * (1.16 + 0.08 * Math.cos(i * 1.7));
    d += `A${n(br)} ${n(br)} 0 0 1 ${n(p[0])} ${n(p[1])}`;
  }
  return `${d}Z`;
}

export const BELL = { cx: 50, cy: 78, r: 4.8 } as const;

/** The bell's needle tip: θ from |0⟩ (up), in the bell's plane. */
export function needle(theta: number, length = 3.9): { x: number; y: number } {
  return { x: BELL.cx + length * Math.sin(theta), y: BELL.cy - length * Math.cos(theta) };
}

/** The Born rule: the chance a measurement finds |0⟩. */
export function probabilityOfZero(theta: number): number {
  return Math.cos(theta / 2) ** 2;
}

/** Measures in the computational basis: 0 for |0⟩, 1 for |1⟩. */
export function measure(theta: number, random: () => number = Math.random): 0 | 1 {
  return random() < probabilityOfZero(theta) ? 0 : 1;
}

const EYE_L = { x: 44.5, y: 61 };
const EYE_R = { x: 55.5, y: 61 };
const MOUTH_Y = 67.5;

function openEye(p: { x: number; y: number }, dx: number, dy: number, r = 2.8): Shape[] {
  return [
    { part: 'face', d: circle(p.x + dx, p.y + dy, r), fill: COLORS.ink },
    {
      part: 'face',
      d: circle(p.x + dx - r * 0.33, p.y + dy - r * 0.36, r * 0.36),
      fill: COLORS.white,
    },
  ];
}

function arcEye(p: { x: number; y: number }, up: boolean): Shape {
  const y = p.y + (up ? 1 : -0.6);
  return {
    part: 'face',
    d: `M${n(p.x - 3.2)} ${n(y)}Q${n(p.x)} ${n(y + (up ? -3.6 : 3))} ${n(p.x + 3.2)} ${n(y)}`,
    stroke: COLORS.ink,
    width: 1.9,
  };
}

function face(kind: Face, look: number): Shape[] {
  const dx = Math.max(-1, Math.min(1, look)) * 1.4;
  const ink = { part: 'face' as const, stroke: COLORS.ink, width: 1.7 };
  const cheeks: Shape[] = [
    { part: 'face', d: ellipse(40.5 + dx * 0.5, 65.5, 2.6, 1.9), fill: COLORS.cheek, opacity: 0.5 },
    { part: 'face', d: ellipse(59.5 + dx * 0.5, 65.5, 2.6, 1.9), fill: COLORS.cheek, opacity: 0.5 },
  ];
  const m = MOUTH_Y;
  const L = { x: EYE_L.x + dx, y: EYE_L.y };
  const R = { x: EYE_R.x + dx, y: EYE_R.y };
  switch (kind) {
    case 'blink':
      return [
        ...cheeks,
        { ...ink, d: `M${n(L.x - 2.8)} ${n(L.y)}h5.6` },
        { ...ink, d: `M${n(R.x - 2.8)} ${n(R.y)}h5.6` },
        { ...ink, d: `M47.5 ${n(m)}Q50 ${n(m + 2.2)} 52.5 ${n(m)}` },
      ];
    case 'happy':
      return [
        ...cheeks,
        arcEye(L, true),
        arcEye(R, true),
        {
          part: 'face',
          d: `M46.6 ${n(m - 0.6)}Q50 ${n(m + 5)} 53.4 ${n(m - 0.6)}Z`,
          fill: COLORS.ink,
        },
        {
          part: 'face',
          d: `M48.2 ${n(m + 1.6)}Q50 ${n(m + 0.7)} 51.8 ${n(m + 1.6)}Q50 ${n(m + 3)} 48.2 ${n(m + 1.6)}Z`,
          fill: COLORS.tongue,
        },
      ];
    case 'thinking':
      return [
        ...cheeks,
        ...openEye(EYE_L, dx + 0.8, -1.6),
        ...openEye(EYE_R, dx + 0.8, -1.6),
        { ...ink, d: `M48 ${n(m + 0.6)}Q50.5 ${n(m - 0.4)} 52.6 ${n(m + 0.2)}` },
      ];
    case 'worried':
      return [
        ...cheeks,
        ...openEye(EYE_L, dx, 0.6, 2.5),
        ...openEye(EYE_R, dx, 0.6, 2.5),
        {
          ...ink,
          width: 1.5,
          d: `M${n(L.x - 3.4)} ${n(L.y - 4.4)}L${n(L.x + 2.2)} ${n(L.y - 5.8)}`,
        },
        {
          ...ink,
          width: 1.5,
          d: `M${n(R.x - 2.2)} ${n(R.y - 5.8)}L${n(R.x + 3.4)} ${n(R.y - 4.4)}`,
        },
        { ...ink, d: `M46.8 ${n(m + 1)}Q48.4 ${n(m - 0.6)} 50 ${n(m + 1)}T53.2 ${n(m + 1)}` },
      ];
    case 'asleep':
      return [
        ...cheeks,
        arcEye(EYE_L, false),
        arcEye(EYE_R, false),
        { part: 'face', d: circle(50, m + 0.6, 1.3), fill: COLORS.ink },
      ];
    case 'surprised':
      return [
        ...cheeks,
        ...openEye(EYE_L, dx, -0.4, 3.3),
        ...openEye(EYE_R, dx, -0.4, 3.3),
        { part: 'face', d: ellipse(50, m + 0.8, 1.7, 2.2), fill: COLORS.ink },
      ];
    case 'awake':
      return [
        ...cheeks,
        ...openEye(EYE_L, dx, 0),
        ...openEye(EYE_R, dx, 0),
        { ...ink, d: `M47.2 ${n(m)}Q50 ${n(m + 2.8)} 52.8 ${n(m)}` },
      ];
  }
}

function marks(kind: Face): Shape[] {
  switch (kind) {
    case 'asleep':
      return [
        { part: 'marks', d: 'M76 14h6l-6 7h6', stroke: COLORS.mark, width: 2 },
        { part: 'marks', d: 'M85 5h4.5l-4.5 5h4.5', stroke: COLORS.mark, width: 1.6 },
      ];
    case 'thinking':
      return [0, 1, 2].map((i) => ({
        part: 'marks' as const,
        d: circle(79 + i * 6, 16 - i * 3, 2.1),
        fill: COLORS.mark,
      }));
    case 'worried':
      return [{ part: 'marks', d: 'M73 32q3.2 5.2 0 7.4q-3.2 -2.2 0 -7.4Z', fill: COLORS.sweat }];
    default:
      return [];
  }
}

// Lumps of wool across the fleece, where the clay was pressed on. Fixed, so Ket always looks the same.
const PUFFS: readonly (readonly [number, number, number])[] = [
  [36, 30, 9],
  [52, 23, 10],
  [67, 31, 8.5],
  [27, 46, 8],
  [74, 47, 8],
  [33, 66, 7.5],
  [68, 67, 7.5],
];

export interface KetPose {
  face: Face;
  /** Where the eyes look, -1 (left) to 1 (right). */
  look?: number;
  /** The bell needle's angle from |0⟩. */
  theta?: number;
  /** The needle turns error red when the notebook has errors. */
  alarm?: boolean;
  /** Small icons have no room for lumps, legs and marks. */
  detail?: boolean;
}

/** Ket in draw order, back to front. */
export function ket(pose: KetPose): Shape[] {
  const detail = pose.detail !== false;
  const tip = needle(pose.theta ?? 0);
  const legs: Shape[] = detail
    ? [36.5, 44.5, 55.5, 63.5].map((x, i) => ({
        part: 'legs' as const,
        d: `M${n(x - 3.4)} 80h6.8v${n(i === 0 || i === 3 ? 8 : 9.5)}a3.4 3.4 0 0 1 -6.8 0Z`,
        fill: { gradient: 'leg' as const },
      }))
    : [];
  const shadow: Shape[] = detail
    ? [{ part: 'shadow', d: ellipse(50, 92.5, 25, 3.6), fill: COLORS.ink, opacity: 0.14 }]
    : [];
  const puffs: Shape[] = detail
    ? PUFFS.map(([x, y, r], i) => ({
        part: 'wool' as const,
        d: cloud(x, y, r, 6, i * 0.7, 0.05),
        fill: { gradient: 'puff' as const },
        opacity: 0.95,
      }))
    : [];
  return [
    ...shadow,
    ...legs,
    {
      part: 'wool',
      d: cloud(51.2, 50.8, 36, 15, 0.15, 0.03),
      fill: COLORS.woolShadow,
      opacity: 0.85,
    },
    { part: 'wool', d: cloud(50, 49, 36, 15, 0.3, 0.035), fill: { gradient: 'wool' } },
    ...puffs,
    // Ears, out to the sides and drooping, half under the fleece.
    { part: 'ears', d: 'M40 58Q30 55.5 27.5 61Q32 65 41 61.5Z', fill: COLORS.ear },
    { part: 'ears', d: 'M38.5 59.4Q32.5 58.6 30.6 61.3Q34 63 39 61.2Z', fill: COLORS.earIn },
    { part: 'ears', d: 'M60 58Q70 55.5 72.5 61Q68 65 59 61.5Z', fill: COLORS.ear },
    { part: 'ears', d: 'M61.5 59.4Q67.5 58.6 69.4 61.3Q66 63 61 61.2Z', fill: COLORS.earIn },
    // The face peeks out of the fleece, under a fringe.
    { part: 'face', d: ellipse(50, 63, 12.6, 11.4), fill: { gradient: 'face' } },
    { part: 'face', d: cloud(50, 52.4, 9.2, 7, -0.25, 0.04), fill: { gradient: 'puff' } },
    ...face(pose.face, pose.look ?? 0),
    // Collar and bell.
    { part: 'bell', d: 'M41.5 73.4Q50 77.6 58.5 73.4', stroke: COLORS.amberDeep, width: 2.2 },
    {
      part: 'bell',
      d: circle(BELL.cx, BELL.cy, BELL.r),
      fill: { gradient: 'bell' },
      stroke: COLORS.amberDeep,
      width: 0.9,
    },
    {
      part: 'bell',
      d: ellipse(BELL.cx, BELL.cy, BELL.r, 1.6),
      stroke: COLORS.amberDeep,
      width: 0.7,
      opacity: 0.8,
    },
    {
      part: 'needle',
      d: `M${n(BELL.cx)} ${n(BELL.cy)}L${n(tip.x)} ${n(tip.y)}`,
      stroke: COLORS.ink,
      width: 1.1,
    },
    {
      part: 'needle',
      d: circle(tip.x, tip.y, 1.35),
      fill: pose.alarm === true ? COLORS.error : COLORS.ink,
    },
    ...(detail ? marks(pose.face) : []),
  ];
}

export const ICON_SIZES = [16, 32, 48, 128] as const;

/** The packaged icon: awake, with every detail where there is room for it. */
export function iconArt(size: number): Shape[] {
  return ket({ face: 'awake', theta: 0.5, detail: size >= 48 });
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
export function toSvg(shapes: readonly Shape[], size: number): string {
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
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${String(VIEW)} ${String(VIEW)}" width="${String(size)}" height="${String(size)}"><defs>${gradientDefs(shapes)}</defs>${paths}</svg>`;
}

export { fillOf };
