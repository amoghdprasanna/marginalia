/**
 * Ket, Marginalia's qubit: the desktop orb's mark (ring, equator, state dot)
 * as a character on a 100×100 canvas. The state dot sits on a Bloch vector,
 * so Ket's moods are states: upright |0⟩ when happy, precessing while it
 * thinks, lying on the equator asleep, and a click measures it.
 *
 * Single source of truth for the panel's SVG and the packaged icons
 * (scripts/generate-icons.ts). No imports, so Node can run it.
 */

export const VIEW = 100;

export const COLORS = {
  body: '#262C42', // the desktop app's raised slate
  amber: '#FFB224', // Marginalia's accent: the qubit, focus, primary buttons
  face: '#ECEFF7',
  error: '#F2735F', // only for "this went wrong"
  halo: '#0A0C16',
} as const;

export const SPHERE = { cx: 50, cy: 54, r: 30 } as const;
/** The equator's height over its width, as on the desktop orb. */
export const TILT = 0.34;
/** The Bloch vector's length, in sphere radii: the dot pokes out of the sphere. */
export const ARM = 1.3;

/** A point on the Bloch sphere: θ from |0⟩ (up), φ around the axis, in radians. */
export interface Bloch {
  theta: number;
  phi: number;
}

export type Face = 'awake' | 'blink' | 'happy' | 'worried' | 'thinking' | 'asleep' | 'surprised';

export interface Shape {
  part: 'halo' | 'vector' | 'body' | 'equator' | 'face' | 'marks';
  d: string;
  fill?: string;
  stroke?: string;
  width?: number;
  opacity?: number;
}

const n = (v: number) => String(Math.round(v * 100) / 100);

export const circle = (cx: number, cy: number, r: number) =>
  `M${n(cx - r)} ${n(cy)}a${n(r)} ${n(r)} 0 1 0 ${n(2 * r)} 0a${n(r)} ${n(r)} 0 1 0 ${n(-2 * r)} 0Z`;

const ellipse = (cx: number, cy: number, rx: number, ry: number) =>
  `M${n(cx - rx)} ${n(cy)}a${n(rx)} ${n(ry)} 0 1 0 ${n(2 * rx)} 0a${n(rx)} ${n(ry)} 0 1 0 ${n(-2 * rx)} 0Z`;

/**
 * Where the state dot lands on screen. The sphere is seen from slightly
 * above, so the front half of the equator is lower; `behind` is true when the
 * vector points away from you and the sphere hides most of it.
 */
export function project(
  s: Bloch,
  length = ARM * SPHERE.r,
): { x: number; y: number; behind: boolean } {
  const x3 = Math.sin(s.theta) * Math.cos(s.phi);
  const y3 = Math.sin(s.theta) * Math.sin(s.phi); // towards you
  const z3 = Math.cos(s.theta);
  const up = Math.sqrt(1 - TILT * TILT);
  return {
    x: SPHERE.cx + length * x3,
    y: SPHERE.cy - length * (z3 * up - y3 * TILT),
    behind: y3 < -1e-9,
  };
}

/** The Born rule: the chance a measurement finds |0⟩. */
export function probabilityOfZero(theta: number): number {
  return Math.cos(theta / 2) ** 2;
}

/** Measures in the computational basis: 0 for |0⟩, 1 for |1⟩. */
export function measure(theta: number, random: () => number = Math.random): 0 | 1 {
  return random() < probabilityOfZero(theta) ? 0 : 1;
}

/** The state each outcome collapses to. */
export const BASIS: Record<0 | 1, Bloch> = {
  0: { theta: 0, phi: 0 },
  1: { theta: Math.PI, phi: 0 },
};

function face(kind: Face, look: number): Shape[] {
  const ink = { stroke: COLORS.face, width: 2.6, part: 'face' as const };
  const dx = Math.max(-1, Math.min(1, look)) * 2.2;
  const lx = 42 + dx;
  const rx = 58 + dx;
  const y = 63;
  switch (kind) {
    case 'blink':
      return [
        { ...ink, d: `M${n(lx - 3.4)} ${n(y)}h6.8` },
        { ...ink, d: `M${n(rx - 3.4)} ${n(y)}h6.8` },
        { ...ink, d: 'M45.5 70.5Q50 73.5 54.5 70.5' },
      ];
    case 'happy':
      return [
        {
          ...ink,
          d: `M${n(lx - 3.4)} ${n(y + 1.4)}Q${n(lx)} ${n(y - 3.6)} ${n(lx + 3.4)} ${n(y + 1.4)}`,
        },
        {
          ...ink,
          d: `M${n(rx - 3.4)} ${n(y + 1.4)}Q${n(rx)} ${n(y - 3.6)} ${n(rx + 3.4)} ${n(y + 1.4)}`,
        },
        { ...ink, d: 'M44 69.5Q50 76 56 69.5' },
      ];
    case 'worried':
      return [
        { part: 'face', d: circle(lx, y + 0.5, 3), fill: COLORS.face },
        { part: 'face', d: circle(rx, y + 0.5, 3), fill: COLORS.face },
        { ...ink, width: 2.2, d: `M${n(lx - 4)} ${n(y - 5)}L${n(lx + 3)} ${n(y - 7)}` },
        { ...ink, width: 2.2, d: `M${n(rx - 3)} ${n(y - 7)}L${n(rx + 4)} ${n(y - 5)}` },
        { ...ink, d: 'M44 72Q47 69.5 50 72T56 72' },
      ];
    case 'thinking':
      return [
        { part: 'face', d: circle(lx + 0.6, y - 2, 3.4), fill: COLORS.face },
        { part: 'face', d: circle(rx + 0.6, y - 2, 3.4), fill: COLORS.face },
        { ...ink, d: 'M47 71.5h6' },
      ];
    case 'asleep':
      return [
        { ...ink, d: `M${n(lx - 3.4)} ${n(y)}Q${n(lx)} ${n(y + 3.4)} ${n(lx + 3.4)} ${n(y)}` },
        { ...ink, d: `M${n(rx - 3.4)} ${n(y)}Q${n(rx)} ${n(y + 3.4)} ${n(rx + 3.4)} ${n(y)}` },
        { ...ink, d: 'M47.5 71.5h5' },
        { part: 'marks', stroke: COLORS.face, width: 2, opacity: 0.7, d: 'M70 22h6l-6 7h6' },
        {
          part: 'marks',
          stroke: COLORS.face,
          width: 1.6,
          opacity: 0.5,
          d: 'M80 12h4.5l-4.5 5h4.5',
        },
      ];
    case 'surprised':
      return [
        { part: 'face', d: circle(lx, y - 0.5, 4), fill: COLORS.face },
        { part: 'face', d: circle(rx, y - 0.5, 4), fill: COLORS.face },
        { ...ink, d: circle(50, 72, 2.6) },
      ];
    case 'awake':
      return [
        { part: 'face', d: circle(lx, y, 3.4), fill: COLORS.face },
        { part: 'face', d: circle(rx, y, 3.4), fill: COLORS.face },
        { ...ink, d: 'M45.5 70.5Q50 73.5 54.5 70.5' },
      ];
  }
}

export interface KetPose {
  state: Bloch;
  face: Face;
  /** Where the eyes look, -1 (left) to 1 (right). */
  look?: number;
  /** The dot turns error red when the notebook has errors. */
  alarm?: boolean;
  /** A dark outline so the ring reads on a white toolbar. */
  halo?: boolean;
  /** Icons at 16 and 32 px have no room for a face. */
  withFace?: boolean;
}

/**
 * Ket in draw order. A vector pointing away from you is drawn before the
 * sphere, so the body hides it the way the far side of a sphere would.
 */
export function ket(pose: KetPose): Shape[] {
  const { cx, cy, r } = SPHERE;
  const tip = project(pose.state);
  const surface = project(pose.state, r);
  const dot = pose.alarm === true ? COLORS.error : COLORS.amber;
  const dim = tip.behind ? 0.5 : 1;
  // Inside the sphere the vector is faint and under the face, so it never
  // crosses Ket's eyes; the part that pokes out is drawn bold.
  const inner: Shape = {
    part: 'vector',
    d: `M${n(cx)} ${n(cy)}L${n(surface.x)} ${n(surface.y)}`,
    stroke: COLORS.amber,
    width: 2,
    opacity: 0.3,
  };
  const outer: Shape[] = [
    {
      part: 'vector',
      d: `M${n(surface.x)} ${n(surface.y)}L${n(tip.x)} ${n(tip.y)}`,
      stroke: COLORS.amber,
      width: 3.4,
      opacity: dim,
    },
    { part: 'vector', d: circle(tip.x, tip.y, 5), fill: dot, opacity: dim },
  ];
  const sphere: Shape[] = [
    ...(pose.halo === true
      ? [
          {
            part: 'halo' as const,
            d: circle(cx, cy, r),
            stroke: COLORS.halo,
            width: 9,
            opacity: 0.45,
          },
        ]
      : []),
    { part: 'body', d: circle(cx, cy, r), fill: COLORS.body, stroke: COLORS.amber, width: 4.2 },
    {
      part: 'equator',
      d: ellipse(cx, cy, r, r * TILT),
      stroke: COLORS.amber,
      width: 1.6,
      opacity: 0.45,
    },
  ];
  const faceShapes = pose.withFace === false ? [] : face(pose.face, pose.look ?? 0);
  return tip.behind
    ? [...outer, ...sphere, inner, ...faceShapes]
    : [...sphere, inner, ...faceShapes, ...outer];
}

export const ICON_SIZES = [16, 32, 48, 128] as const;

/** The packaged icon: awake, the vector leaning a little right and towards you. */
export function iconArt(size: number): Shape[] {
  return ket({
    state: { theta: 0.55, phi: 0.5 },
    face: 'awake',
    halo: true,
    withFace: size >= 48,
  });
}

/**
 * Draws shapes on a 2D canvas scaled from the 100-unit view. Self-contained
 * (no closures over this module), because the icon script sends its source
 * into a browser page.
 */
export function paint(
  ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D,
  shapes: readonly Shape[],
  size: number,
  makePath: (d: string) => Path2D,
): void {
  ctx.clearRect(0, 0, size, size);
  ctx.save();
  ctx.scale(size / 100, size / 100);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  for (const s of shapes) {
    const path = makePath(s.d);
    ctx.globalAlpha = s.opacity ?? 1;
    if (s.fill !== undefined) {
      ctx.fillStyle = s.fill;
      ctx.fill(path);
    }
    if (s.stroke !== undefined) {
      ctx.strokeStyle = s.stroke;
      ctx.lineWidth = s.width ?? 1;
      ctx.stroke(path);
    }
  }
  ctx.restore();
}
