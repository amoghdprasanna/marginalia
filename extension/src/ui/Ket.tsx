import { useEffect, useId, useRef, useState, type CSSProperties } from 'react';
import {
  GRADIENTS,
  ket,
  measure,
  VIEW,
  type Face,
  type Gradient,
  type Part,
  type Shape,
} from '@/src/mascot/ket';

/** What the panel is doing, which Ket shows. */
export type Mood = 'asleep' | 'awake' | 'thinking' | 'happy' | 'worried';

const MOOD_FACE: Record<Mood, Face> = {
  asleep: 'asleep',
  awake: 'awake',
  thinking: 'thinking',
  happy: 'happy',
  worried: 'worried',
};

/**
 * Ket's mood as a qubit state, θ from |0⟩: what a click "measures". Content is |0⟩, an error
 * knocks it most of the way to |1⟩, and the rest sit in between.
 */
const MOOD_THETA: Record<Mood, number> = {
  asleep: Math.PI / 2,
  awake: 0.45,
  thinking: 0.6,
  happy: 0,
  worried: 2.3,
};

const BLINK_MS = 140;
const MEASURED_MS = 1500;
const HOP_MS = 650;
const SPIN_MS = 800;
/** Three clicks within this window: a full roll instead of a measurement. */
const SPIN_WINDOW_MS = 900;

type Anim = 'hop' | 'spin' | 'ring' | null;

/** Consecutive shapes of one part, so each part is one animatable group. */
function groups(shapes: readonly Shape[]): { part: Part; shapes: Shape[] }[] {
  const out: { part: Part; shapes: Shape[] }[] = [];
  for (const s of shapes) {
    const last = out.at(-1);
    if (last?.part === s.part) last.shapes.push(s);
    else out.push({ part: s.part, shapes: [s] });
  }
  return out;
}

function Defs({ prefix }: { prefix: string }) {
  return (
    <defs>
      {Object.entries(GRADIENTS).map(([id, g]: [string, Gradient]) => (
        <radialGradient key={id} id={`${prefix}-${id}`} cx={g.cx} cy={g.cy} r={g.r}>
          {g.stops.map(([o, c]) => (
            <stop key={o} offset={o} stopColor={c} />
          ))}
        </radialGradient>
      ))}
    </defs>
  );
}

/**
 * Ket, the lamb. It breathes, blinks, looks toward the pointer and perks its ears when you
 * hover. It looks up while Marginalia reads or Claude works, is content when the notebook is
 * clean and frets when a cell raised. It hops when a fix lands. A click measures it, with the
 * Born rule's odds for its mood, and shows |0⟩ or |1⟩; three quick clicks make it turn round.
 * All motion is CSS, and none of it runs with reduced motion.
 */
export function Ket({
  mood,
  size = 72,
  celebrate = 0,
}: {
  mood: Mood;
  size?: number;
  celebrate?: number;
}) {
  const prefix = `ket${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const ref = useRef<HTMLButtonElement>(null);
  const clicks = useRef<number[]>([]);
  const [look, setLook] = useState(0);
  const [hover, setHover] = useState(false);
  const [blinking, setBlinking] = useState(false);
  const [anim, setAnim] = useState<Anim>(null);
  const [measured, setMeasured] = useState<0 | 1 | null>(null);
  const [lastCelebrate, setLastCelebrate] = useState(celebrate);

  // A fix landed: hop. (Adjusted during render, so it starts on the same frame.)
  if (celebrate !== lastCelebrate) {
    setLastCelebrate(celebrate);
    setAnim('hop');
  }

  useEffect(() => {
    if (anim === null) return;
    const t = window.setTimeout(
      () => {
        setAnim(null);
      },
      anim === 'spin' ? SPIN_MS : HOP_MS,
    );
    return () => {
      window.clearTimeout(t);
    };
  }, [anim]);

  useEffect(() => {
    if (measured === null) return;
    const t = window.setTimeout(() => {
      setMeasured(null);
    }, MEASURED_MS);
    return () => {
      window.clearTimeout(t);
    };
  }, [measured]);

  // Eyes follow the pointer anywhere in the panel.
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const box = ref.current?.getBoundingClientRect();
      if (box === undefined) return;
      setLook(Math.max(-1, Math.min(1, (e.clientX - (box.left + box.width / 2)) / 160)));
    };
    const onLeave = () => {
      setLook(0);
    };
    window.addEventListener('pointermove', onMove);
    document.documentElement.addEventListener('pointerleave', onLeave);
    return () => {
      window.removeEventListener('pointermove', onMove);
      document.documentElement.removeEventListener('pointerleave', onLeave);
    };
  }, []);

  // A blink every few seconds while awake.
  useEffect(() => {
    if (mood === 'asleep') return;
    let timer: number;
    const schedule = () => {
      timer = window.setTimeout(
        () => {
          if (document.hidden) {
            schedule();
            return;
          }
          setBlinking(true);
          timer = window.setTimeout(() => {
            setBlinking(false);
            schedule();
          }, BLINK_MS);
        },
        2600 + Math.random() * 3400,
      );
    };
    schedule();
    return () => {
      window.clearTimeout(timer);
    };
  }, [mood]);

  const theta = measured !== null ? measured * Math.PI : MOOD_THETA[mood];

  const onClick = () => {
    const now = performance.now();
    clicks.current = [...clicks.current.filter((t) => now - t < SPIN_WINDOW_MS), now];
    if (clicks.current.length >= 3) {
      clicks.current = [];
      setMeasured(null);
      setAnim('spin');
      return;
    }
    setMeasured(measure(theta));
    setAnim('ring');
  };

  let face: Face = MOOD_FACE[mood];
  if (measured !== null) face = 'surprised';
  else if (anim === 'hop' || anim === 'spin') face = 'happy';
  else if (blinking) face = 'blink';
  else if (hover && mood === 'awake') face = 'happy';

  const shapes = ket({ face, look });
  const parts = groups(shapes);

  const paths = (list: Shape[]) =>
    list.map((s, i) => (
      <path
        key={i}
        d={s.d}
        fill={
          s.fill === undefined
            ? 'none'
            : typeof s.fill === 'string'
              ? s.fill
              : `url(#${prefix}-${s.fill.gradient})`
        }
        stroke={s.stroke}
        strokeWidth={s.width}
        opacity={s.opacity}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    ));

  return (
    <div
      className="ket"
      data-mood={mood}
      data-anim={anim ?? undefined}
      data-hover={hover ? '' : undefined}
    >
      <button
        ref={ref}
        type="button"
        className="ket-button"
        onClick={onClick}
        onPointerEnter={() => {
          setHover(true);
        }}
        onPointerLeave={() => {
          setHover(false);
        }}
        aria-label="Ket, Marginalia's sheep. Click to measure it."
        style={{ width: size, height: size }}
      >
        <svg
          viewBox={`0 0 ${String(VIEW)} ${String(VIEW)}`}
          width={size}
          height={size}
          aria-hidden="true"
          style={{ '--look': String(look) } as CSSProperties}
        >
          <Defs prefix={prefix} />
          {parts
            .filter((g) => g.part === 'shadow')
            .map((g, i) => (
              <g key={`shadow${String(i)}`} className="ket-shadow">
                {paths(g.shapes)}
              </g>
            ))}
          <g className="ket-body">
            {parts
              .filter((g) => g.part !== 'shadow')
              .map((g, i) => (
                <g key={`${g.part}${String(i)}`} className={`ket-${g.part}`}>
                  {paths(g.shapes)}
                </g>
              ))}
          </g>
        </svg>
      </button>
      <span className="ket-said" aria-live="polite">
        {measured === null ? '' : measured === 0 ? '|0⟩' : '|1⟩'}
      </span>
    </div>
  );
}
