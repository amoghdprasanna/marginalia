import type { FixReply } from '@/src/adapters/helper';
import type { CellError } from '@/src/core/notebook';

/**
 * One notebook's session with Claude: each suggestion and what you did with it, oldest
 * first. Sent with every fix, so Claude builds on what was tried (docs/adr/0032).
 */
export type Outcome = 'proposed' | 'applied' | 'undone' | 'dismissed';

export interface Attempt {
  /** The error it was for (CellError.key). */
  key: string;
  /** The cell's number, from 1. */
  cell: number;
  ename: string;
  evalue: string;
  summary: string;
  kind: FixReply['fix']['kind'];
  source: string;
  outcome: Outcome;
}

/** Enough for Claude to see the thread of a debugging session without drowning in it. */
export const SESSION_LIMIT = 10;

export function proposed(
  session: readonly Attempt[],
  error: CellError,
  reply: FixReply,
): Attempt[] {
  const attempt: Attempt = {
    key: error.key,
    cell: error.index + 1,
    ename: error.ename,
    evalue: error.evalue.slice(0, 500),
    summary: reply.summary,
    kind: reply.fix.kind,
    source: reply.fix.source.slice(0, 2000),
    outcome: 'proposed',
  };
  // Asking again about the same error replaces its earlier, unused suggestion.
  const kept = session.filter((a) => !(a.key === error.key && a.outcome === 'proposed'));
  return [...kept, attempt].slice(-SESSION_LIMIT);
}

/** Marks the latest suggestion for `key` with what happened to it. */
export function settle(session: readonly Attempt[], key: string, outcome: Outcome): Attempt[] {
  const i = session.map((a) => a.key).lastIndexOf(key);
  if (i < 0) return [...session];
  return session.map((a, j) => (j === i ? { ...a, outcome } : a));
}
