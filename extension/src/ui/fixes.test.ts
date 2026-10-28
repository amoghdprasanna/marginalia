import { describe, expect, it } from 'vitest';
import type { FixReply } from '@/src/adapters/helper';
import type { CellError } from '@/src/core/notebook';
import { appliedText, editFor, fixKey, proposalFor, undoFor } from './fixes';

const error: CellError = {
  index: 3,
  cellId: 'c4',
  executionCount: 5,
  ename: 'ModuleNotFoundError',
  evalue: "No module named 'qutip'",
  traceback: '',
  where: null,
  line: null,
  raisedIn: null,
  source: 'import qutip as qt',
};

const reply = (kind: FixReply['fix']['kind'], source: string): FixReply => ({
  type: 'fix',
  summary: 's',
  explanation: 'e',
  fix: { kind, source },
  model: 'm',
});

describe('fix edits', () => {
  it('replace applies against the source Claude saw, and undo puts it back', () => {
    const p = proposalFor(error, reply('replace', 'import qutip'));
    expect(editFor(p)).toEqual({
      kind: 'replace',
      index: 3,
      cellId: 'c4',
      expected: 'import qutip as qt',
      source: 'import qutip',
    });
    expect(undoFor(p, 'c4')).toEqual({
      kind: 'replace',
      index: 3,
      cellId: 'c4',
      expected: 'import qutip',
      source: 'import qutip as qt',
    });
    expect(appliedText(p)).toBe('Changed cell 4. Run it to check.');
  });

  it('insert_before undoes by deleting the cell it added', () => {
    const p = proposalFor(error, reply('insert_before', '%pip install qutip'));
    expect(editFor(p)).toEqual({
      kind: 'insert_before',
      index: 3,
      cellId: 'c4',
      source: '%pip install qutip',
    });
    expect(undoFor(p, 'new-1')).toEqual({
      kind: 'delete',
      cellId: 'new-1',
      expected: '%pip install qutip',
    });
    expect(undoFor(p, null)).toBeNull();
    expect(appliedText(p)).toContain('Added a cell before cell 4');
  });

  it('a fix outside the notebook has nothing to apply', () => {
    expect(editFor(proposalFor(error, reply('none', '')))).toBeNull();
  });

  it('keys errors by cell id, else position', () => {
    expect(fixKey(error)).toBe('c4');
    expect(fixKey({ cellId: null, index: 2 })).toBe('#2');
  });
});
