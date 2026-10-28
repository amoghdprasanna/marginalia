/**
 * Ket, Marginalia's mascot: an enormous round fleece with a small dark face peeking out,
 * placid half-lidded eyes and stubby legs, in a soft hand-made clay look,
 * on a 100×100 canvas. Its collar bell is a little Bloch sphere: the bell's needle is the
 * qubit's state, so a click "measures" it with the Born rule.
 *
 * Single source of truth for the panel (React maps the shapes) and the packaged icons
 * (scripts/generate-icons.ts renders `toSvg`). No imports, so Node can run it.
 */

export const VIEW = 100;

export const COLORS = {
  ink: '#1B1B22',
  white: '#FFFFFF',
  sclera: '#F7F4EF',
  faceInk: '#F1ECE6', // lines drawn on the dark face
  woolShadow: '#C9BCA7',
  ear: '#4A4550',
  earIn: '#C99A9A',
  cheek: '#E58C8C',
  tongue: '#E8778A',
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
    cx: 0.42,
    cy: 0.3,
    r: 0.85,
    stops: [
      [0, '#6E6774'],
      [1, '#3C3742'],
    ],
  },
  leg: {
    cx: 0.35,
    cy: 0.25,
    r: 0.9,
    stops: [
      [0, '#5A5460'],
      [1, '#2E2A33'],
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

export const BELL = { cx: 50, cy: 76.5, r: 4.4 } as const;

/** The bell's needle tip: θ from |0⟩ (up), in the bell's plane. */
export function needle(theta: number, length = 3.6): { x: number; y: number } {
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

// The face: small and dark, low in an enormous fleece, eyes set close like a sheep's.
const FACE = { cx: 50, cy: 61, rx: 12, ry: 12.2 } as const;
const EYE_L = { x: 45.3, y: 59.8 };
const EYE_R = { x: 54.7, y: 59.8 };
const MOUTH_Y = 67.2;

/**
 * An eye: white, a dark pupil looking `dx` sideways, a glint, and an upper lid that covers
 * `lid` of it (0 open, 0.5 the placid half-closed look).
 */
function eye(p: { x: number; y: number }, dx: number, dy: number, lid: number, r = 3.2): Shape[] {
  const shapes: Shape[] = [
    { part: 'face', d: circle(p.x, p.y, r), fill: COLORS.sclera },
    { part: 'face', d: circle(p.x + dx * 0.9, p.y + 0.3 + dy, r * 0.56), fill: COLORS.ink },
    {
      part: 'face',
      d: circle(p.x + dx * 0.9 - 0.55, p.y - 0.35 + dy, r * 0.2),
      fill: COLORS.white,
    },
  ];
  if (lid > 0) {
    // The lid: the top of the eye in face colour, with a soft line along its edge.
    const y = p.y - r + 2 * r * lid;
    shapes.push(
      {
        part: 'face',
        d: `M${n(p.x - r - 0.3)} ${n(y)}A${n(r + 0.3)} ${n(r + 0.3)} 0 0 1 ${n(p.x + r + 0.3)} ${n(y)}Z`,
        fill: '#57515D',
      },
      {
        part: 'face',
        d: `M${n(p.x - r)} ${n(y)}Q${n(p.x)} ${n(y + 0.7)} ${n(p.x + r)} ${n(y)}`,
        stroke: COLORS.ink,
        width: 0.7,
        opacity: 0.6,
      },
    );
  }
  return shapes;
}

function arcEye(p: { x: number; y: number }, up: boolean): Shape {
  const y = p.y + (up ? 0.8 : -0.4);
  return {
    part: 'face',
    d: `M${n(p.x - 2.6)} ${n(y)}Q${n(p.x)} ${n(y + (up ? -3 : 2.6))} ${n(p.x + 2.6)} ${n(y)}`,
    stroke: COLORS.faceInk,
    width: 1.5,
  };
}

function face(kind: Face, look: number): Shape[] {
  const dx = Math.max(-1, Math.min(1, look));
  const line = { part: 'face' as const, stroke: COLORS.faceInk, width: 1.3 };
  const nose: Shape[] = [
    { part: 'face', d: ellipse(48.4, 64.8, 0.8, 0.5), fill: COLORS.ink, opacity: 0.7 },
    { part: 'face', d: ellipse(51.6, 64.8, 0.8, 0.5), fill: COLORS.ink, opacity: 0.7 },
  ];
  const cheeks: Shape[] = [
    { part: 'face', d: ellipse(41.6, 64.6, 2.1, 1.4), fill: COLORS.cheek, opacity: 0.45 },
    { part: 'face', d: ellipse(58.4, 64.6, 2.1, 1.4), fill: COLORS.cheek, opacity: 0.45 },
  ];
  const m = MOUTH_Y;
  const smile = { ...line, d: `M48 ${n(m)}Q50 ${n(m + 1.8)} 52 ${n(m)}` };
  switch (kind) {
    case 'awake':
      return [...eye(EYE_L, dx, 0, 0.42), ...eye(EYE_R, dx, 0, 0.42), ...nose, ...cheeks, smile];
    case 'blink':
      return [
        { ...line, d: `M${n(EYE_L.x - 2.6)} ${n(EYE_L.y + 0.6)}h5.2` },
        { ...line, d: `M${n(EYE_R.x - 2.6)} ${n(EYE_R.y + 0.6)}h5.2` },
        ...nose,
        ...cheeks,
        smile,
      ];
    case 'happy':
      return [
        arcEye(EYE_L, true),
        arcEye(EYE_R, true),
        ...nose,
        ...cheeks,
        {
          part: 'face',
          d: `M47.4 ${n(m - 0.4)}Q50 ${n(m + 4)} 52.6 ${n(m - 0.4)}Z`,
          fill: COLORS.ink,
        },
        {
          part: 'face',
          d: `M48.6 ${n(m + 1.3)}Q50 ${n(m + 0.6)} 51.4 ${n(m + 1.3)}Q50 ${n(m + 2.5)} 48.6 ${n(m + 1.3)}Z`,
          fill: COLORS.tongue,
        },
      ];
    case 'thinking':
      return [
        ...eye(EYE_L, 0.4, -1.1, 0.2),
        ...eye(EYE_R, 0.4, -1.1, 0.2),
        ...nose,
        ...cheeks,
        { ...line, d: `M48.4 ${n(m + 0.5)}Q50.4 ${n(m - 0.3)} 52 ${n(m + 0.2)}` },
      ];
    case 'worried':
      return [
        ...eye(EYE_L, dx, 0.3, 0, 2.5),
        ...eye(EYE_R, dx, 0.3, 0, 2.5),
        {
          ...line,
          width: 1.1,
          d: `M${n(EYE_L.x - 3)} ${n(EYE_L.y - 3.6)}L${n(EYE_L.x + 1.6)} ${n(EYE_L.y - 4.9)}`,
        },
        {
          ...line,
          width: 1.1,
          d: `M${n(EYE_R.x - 1.6)} ${n(EYE_R.y - 4.9)}L${n(EYE_R.x + 3)} ${n(EYE_R.y - 3.6)}`,
        },
        ...nose,
        {
          ...line,
          d: `M47.6 ${n(m + 0.9)}Q48.8 ${n(m - 0.4)} 50 ${n(m + 0.9)}T52.4 ${n(m + 0.9)}`,
        },
      ];
    case 'asleep':
      return [arcEye(EYE_L, false), arcEye(EYE_R, false), ...nose, ...cheeks];
    case 'surprised':
      return [
        ...eye(EYE_L, 0, 0, 0, 3.1),
        ...eye(EYE_R, 0, 0, 0, 3.1),
        ...nose,
        { part: 'face', d: ellipse(50, m + 0.6, 1.3, 1.7), fill: COLORS.ink },
      ];
  }
}

function marks(kind: Face): Shape[] {
  switch (kind) {
    case 'asleep':
      return [
        { part: 'marks', d: 'M78 12h6l-6 7h6', stroke: COLORS.mark, width: 2 },
        { part: 'marks', d: 'M87 3h4.5l-4.5 5h4.5', stroke: COLORS.mark, width: 1.6 },
      ];
    case 'thinking':
      return [0, 1, 2].map((i) => ({
        part: 'marks' as const,
        d: circle(80 + i * 6, 14 - i * 3, 2.1),
        fill: COLORS.mark,
      }));
    case 'worried':
      return [{ part: 'marks', d: 'M72 30q3.2 5.2 0 7.4q-3.2 -2.2 0 -7.4Z', fill: COLORS.sweat }];
    default:
      return [];
  }
}

// Lumps across the fleece, where the clay was pressed on. Fixed, so Ket always looks the same.
const PUFFS: readonly (readonly [number, number, number])[] = [
  [34, 24, 8.5],
  [50, 17, 9.5],
  [66, 24, 8.5],
  [24, 39, 8],
  [76, 39, 8],
  [21, 56, 7.5],
  [79, 56, 7.5],
  [30, 70, 7],
  [70, 70, 7],
  [42, 33, 7],
  [58, 33, 7],
  [50, 43, 6.5],
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
    ? [39, 45.5, 54.5, 61].map((x, i) => ({
        part: 'legs' as const,
        d: `M${n(x - 2.6)} 81h5.2v${n(i === 0 || i === 3 ? 6.5 : 7.5)}a2.6 2.6 0 0 1 -5.2 0Z`,
        fill: { gradient: 'leg' as const },
      }))
    : [];
  const shadow: Shape[] = detail
    ? [{ part: 'shadow', d: ellipse(50, 92, 27, 3.6), fill: COLORS.ink, opacity: 0.16 }]
    : [];
  const puffs: Shape[] = detail
    ? PUFFS.map(([x, y, r], i) => ({
        part: 'wool' as const,
        d: cloud(x, y, r, 7, i * 0.7, 0.05),
        fill: { gradient: 'puff' as const },
        opacity: 0.92,
      }))
    : [];
  return [
    ...shadow,
    ...legs,
    // An enormous round fleece: nearly the whole canvas, curls all the way round.
    {
      part: 'wool',
      d: cloud(51.4, 49.2, 40, 20, 0.12, 0.025),
      fill: COLORS.woolShadow,
      opacity: 0.9,
    },
    { part: 'wool', d: cloud(50, 47.6, 40, 20, 0.28, 0.03), fill: { gradient: 'wool' } },
    ...puffs,
    // Small dark ears, out to the sides, just under the fleece.
    { part: 'ears', d: 'M41 57.4Q34.5 55.2 32.4 58.6Q35.6 61.6 41.4 60.2Z', fill: COLORS.ear },
    { part: 'ears', d: 'M39.6 58.2Q35.6 57.2 34.4 58.9Q36.6 60.3 39.8 59.6Z', fill: COLORS.earIn },
    { part: 'ears', d: 'M59 57.4Q65.5 55.2 67.6 58.6Q64.4 61.6 58.6 60.2Z', fill: COLORS.ear },
    { part: 'ears', d: 'M60.4 58.2Q64.4 57.2 65.6 58.9Q63.4 60.3 60.2 59.6Z', fill: COLORS.earIn },
    // The face peeks out of the fleece, under a thick fringe.
    { part: 'face', d: ellipse(FACE.cx, FACE.cy, FACE.rx, FACE.ry), fill: { gradient: 'face' } },
    { part: 'face', d: cloud(50, 50.4, 12, 8, -0.2, 0.05), fill: { gradient: 'puff' } },
    ...face(pose.face, pose.look ?? 0),
    // Collar and bell.
    { part: 'bell', d: 'M43 71.8Q50 75.6 57 71.8', stroke: COLORS.amberDeep, width: 1.9 },
    {
      part: 'bell',
      d: circle(BELL.cx, BELL.cy, BELL.r),
      fill: { gradient: 'bell' },
      stroke: COLORS.amberDeep,
      width: 0.8,
    },
    {
      part: 'bell',
      d: ellipse(BELL.cx, BELL.cy, BELL.r, 1.45),
      stroke: COLORS.amberDeep,
      width: 0.6,
      opacity: 0.8,
    },
    {
      part: 'needle',
      d: `M${n(BELL.cx)} ${n(BELL.cy)}L${n(tip.x)} ${n(tip.y)}`,
      stroke: COLORS.ink,
      width: 1,
    },
    {
      part: 'needle',
      d: circle(tip.x, tip.y, 1.2),
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
