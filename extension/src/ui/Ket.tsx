import { useEffect, useRef, useState } from 'react';
import { BASIS, ket, measure, VIEW, type Bloch, type Face, type Shape } from '@/src/mascot/ket';

/** What the panel is doing, which Ket shows as a state. */
export type Mood = 'asleep' | 'awake' | 'thinking' | 'happy' | 'worried';

const BLINK_MS = 140;
/** One turn of precession while thinking. */
const PRECESSION_MS = 1600;
/** How long a measured state holds before Ket relaxes. */
const MEASURED_MS = 1400;
/** Three clicks within this window: a full Rabi flop instead of a measurement. */
const FLOP_WINDOW_MS = 900;
const FLOP_MS = 1100;
/** How far Ket leans toward the pointer, at most. */
const MAX_LEAN = 0.6;

const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Where each mood points the Bloch vector, `t` in ms for the ones that move. */
function moodState(mood: Mood, lean: number, t: number, still: boolean): Bloch {
  switch (mood) {
    case 'asleep':
      return { theta: Math.PI / 2, phi: Math.PI }; // lying on the equator
    case 'thinking':
      return { theta: 0.62, phi: still ? 0.8 : (2 * Math.PI * t) / PRECESSION_MS };
    case 'happy':
      return { theta: 0, phi: 0 };
    case 'worried':
      return { theta: 0.95, phi: 0 }; // knocked off |0⟩
    case 'awake':
      return { theta: Math.abs(lean) * MAX_LEAN, phi: lean < 0 ? Math.PI : 0 };
  }
}

const MOOD_FACE: Record<Mood, Face> = {
  asleep: 'asleep',
  awake: 'awake',
  thinking: 'thinking',
  happy: 'happy',
  worried: 'worried',
};

/** Shortest way round, so φ never spins the long way. */
function approachAngle(from: number, to: number, k: number): number {
  const d = Math.atan2(Math.sin(to - from), Math.cos(to - from));
  return from + d * k;
}

function Paths({ shapes }: { shapes: readonly Shape[] }) {
  return shapes.map((s, i) => (
    <path
      key={i}
      d={s.d}
      fill={s.fill ?? 'none'}
      stroke={s.stroke}
      strokeWidth={s.width}
      opacity={s.opacity}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ));
}

type Event =
  { kind: 'measured'; outcome: 0 | 1; until: number } | { kind: 'flop'; start: number } | null;

/**
 * Ket leans toward the pointer and its eyes follow it, blinks now and then,
 * precesses while Marginalia works, stands up in |0⟩ when the notebook is
 * clean, gets knocked over by errors and lies down asleep when there is
 * nothing to read. A click measures it, with the Born rule's odds; three
 * quick clicks drive a full Rabi flop. Reduced motion: no animation, the
 * same states.
 */
export function Ket({ mood, size = 64 }: { mood: Mood; size?: number }) {
  const ref = useRef<HTMLButtonElement>(null);
  const clicks = useRef<number[]>([]);
  const [pose, setPose] = useState<Bloch>(() => moodState(mood, 0, 0, true));
  const current = useRef(pose);
  const [lean, setLean] = useState(0);
  const [blinking, setBlinking] = useState(false);
  const [event, setEvent] = useState<Event>(null);
  const [said, setSaid] = useState<string | null>(null);

  // Lean and look toward the pointer anywhere in the panel.
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const box = ref.current?.getBoundingClientRect();
      if (box === undefined) return;
      const dx = e.clientX - (box.left + box.width / 2);
      setLean(Math.max(-1, Math.min(1, dx / 220)));
    };
    const onLeave = () => setLean(0);
    window.addEventListener('pointermove', onMove);
    document.documentElement.addEventListener('pointerleave', onLeave);
    return () => {
      window.removeEventListener('pointermove', onMove);
      document.documentElement.removeEventListener('pointerleave', onLeave);
    };
  }, []);

  // Blink every few seconds while awake; never while the panel is hidden.
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
        2800 + Math.random() * 3600,
      );
    };
    schedule();
    return () => window.clearTimeout(timer);
  }, [mood]);

  // Move toward the target state; the loop stops once Ket is still. The pose
  // lives in a ref too, so each frame decides synchronously whether to go on.
  useEffect(() => {
    const still = reducedMotion();
    let frame = 0;
    const show = (next: Bloch) => {
      current.current = next;
      setPose(next);
    };
    const step = (now: number) => {
      if (event?.kind === 'flop') {
        const p = Math.min(1, (now - event.start) / FLOP_MS);
        const eased = p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2;
        show({ theta: 2 * Math.PI * eased, phi: 0 });
        if (p >= 1) {
          show({ theta: 0, phi: 0 });
          setEvent(null);
        } else frame = requestAnimationFrame(step);
        return;
      }
      if (event?.kind === 'measured' && now >= event.until) {
        setEvent(null);
        setSaid(null);
        return; // the effect restarts without the event
      }
      const target =
        event?.kind === 'measured' ? BASIS[event.outcome] : moodState(mood, lean, now, still);
      const moving = mood === 'thinking' && event === null && !still;
      if (still) {
        show(target);
      } else {
        const cur = current.current;
        const next = {
          theta: cur.theta + (target.theta - cur.theta) * 0.16,
          phi: moving ? target.phi : approachAngle(cur.phi, target.phi, 0.16),
        };
        const settled =
          Math.abs(next.theta - target.theta) < 0.002 &&
          Math.abs(Math.sin(next.phi - target.phi)) < 0.002;
        show(settled ? target : next);
        if (settled && !moving && event === null) return;
      }
      // A measured state waits for its timer even when still.
      if (event !== null || moving || !still) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [mood, lean, event]);

  const onClick = () => {
    const now = performance.now();
    clicks.current = [...clicks.current.filter((t) => now - t < FLOP_WINDOW_MS), now];
    if (clicks.current.length >= 3) {
      clicks.current = [];
      setSaid(null);
      setEvent(reducedMotion() ? null : { kind: 'flop', start: now });
      return;
    }
    const outcome = measure(current.current.theta);
    setSaid(outcome === 0 ? '|0⟩' : '|1⟩');
    setEvent({ kind: 'measured', outcome, until: now + MEASURED_MS });
  };

  const face: Face =
    event?.kind === 'measured'
      ? 'surprised'
      : event?.kind === 'flop'
        ? 'happy'
        : blinking
          ? 'blink'
          : MOOD_FACE[mood];
  const shapes = ket({
    state: pose,
    face,
    look: lean,
    alarm: mood === 'worried' && event === null,
  });

  return (
    <div className="ket">
      <button
        ref={ref}
        type="button"
        className="ket-button"
        onClick={onClick}
        aria-label="Ket, Marginalia's qubit. Click to measure it."
        style={{ width: size, height: size }}
      >
        <svg
          viewBox={`0 0 ${String(VIEW)} ${String(VIEW)}`}
          width={size}
          height={size}
          aria-hidden="true"
        >
          <Paths shapes={shapes} />
        </svg>
        {event?.kind === 'measured' && <span className="ket-flash" aria-hidden="true" />}
      </button>
      <span className="ket-said" aria-live="polite">
        {said}
      </span>
    </div>
  );
}
