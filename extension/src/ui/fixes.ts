import type { FixReply, HelperProblem } from '@/src/adapters/helper';
import type { CellError } from '@/src/core/notebook';
import type { EditOp } from '@/src/messaging/protocol';

/**
 * One error's fix, from asking Claude to undoing what you applied (docs/adr/0030).
 * Nothing changes in the notebook until Apply, and nothing ever runs.
 */
export type FixState =
  | { kind: 'idle' }
  | { kind: 'asking'; since: number }
  | { kind: 'proposed'; proposal: Proposal }
  | { kind: 'applying'; proposal: Proposal }
  | { kind: 'applied'; proposal: Proposal; undo: EditOp }
  | { kind: 'undoing'; proposal: Proposal; undo: EditOp }
  | {
      kind: 'failed';
      message: string;
      problem: HelperProblem | 'stale' | 'gone' | 'unavailable';
      action: 'retry' | 'settings' | null;
    };

/** Claude's answer, and the cell as it was when Claude saw it. */
export interface Proposal {
  reply: FixReply;
  index: number;
  cellId: string | null;
  /** The failing cell's number for people: "cell 4". */
  cellNumber: number;
  expected: string;
}

/** Errors are keyed by cell id (stable while you edit), else position. */
export const fixKey = (e: Pick<CellError, 'cellId' | 'index'>): string =>
  e.cellId ?? `#${String(e.index)}`;

export function proposalFor(error: CellError, reply: FixReply): Proposal {
  return {
    reply,
    index: error.index,
    cellId: error.cellId,
    cellNumber: error.index + 1,
    expected: error.source,
  };
}

/** The edit Apply makes; null when Claude's fix is outside the notebook. */
export function editFor(p: Proposal): EditOp | null {
  const { kind, source } = p.reply.fix;
  if (kind === 'replace')
    return { kind: 'replace', index: p.index, cellId: p.cellId, expected: p.expected, source };
  if (kind === 'insert_before')
    return { kind: 'insert_before', index: p.index, cellId: p.cellId, source };
  return null;
}

/** The edit that takes it back, given the cell the page reported changing or adding. */
export function undoFor(p: Proposal, changedCellId: string | null): EditOp | null {
  const { kind, source } = p.reply.fix;
  if (kind === 'replace')
    return {
      kind: 'replace',
      index: p.index,
      cellId: changedCellId ?? p.cellId,
      expected: source,
      source: p.expected,
    };
  if (kind === 'insert_before' && changedCellId !== null)
    return { kind: 'delete', cellId: changedCellId, expected: source };
  return null;
}

/** What Apply did, in words: the line under an applied fix. */
export function appliedText(p: Proposal): string {
  return p.reply.fix.kind === 'insert_before'
    ? `Added a cell before cell ${String(p.cellNumber)}. Run it, then run cell ${String(p.cellNumber)} again.`
    : `Changed cell ${String(p.cellNumber)}. Run it to check.`;
}
