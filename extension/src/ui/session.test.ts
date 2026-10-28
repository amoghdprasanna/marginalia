import { describe, expect, it } from 'vitest';
import type { FixReply } from '@/src/adapters/helper';
import type { CellError } from '@/src/core/notebook';
import { proposed, SESSION_LIMIT, settle } from './session';

const error = (key: string, index = 1): CellError => ({
  key,
  index,
  cellId: 'c',
  executionCount: 1,
  ename: 'ModuleNotFoundError',
  evalue: "No module named 'qutip'",
  traceback: '',
  where: null,
  line: null,
  raisedIn: null,
  source: 'import qutip',
});

const reply: FixReply = {
  type: 'fix',
  summary: "qutip isn't installed.",
  explanation: '',
  fix: { kind: 'insert_before', source: '%pip install qutip' },
  model: 'm',
};

describe('the session', () => {
  it('records a suggestion, then what you did with it', () => {
    let s = proposed([], error('a'), reply);
    expect(s).toMatchObject([{ key: 'a', cell: 2, kind: 'insert_before', outcome: 'proposed' }]);
    s = settle(s, 'a', 'applied');
    expect(s[0]?.outcome).toBe('applied');
    s = settle(s, 'a', 'undone');
    expect(s[0]?.outcome).toBe('undone');
  });

  it('replaces an unused suggestion when you ask again, but keeps ones you acted on', () => {
    let s = proposed([], error('a'), reply);
    s = proposed(s, error('a'), reply);
    expect(s).toHaveLength(1);
    s = settle(s, 'a', 'applied');
    s = proposed(s, error('b'), reply);
    expect(s.map((a) => [a.key, a.outcome])).toEqual([
      ['a', 'applied'],
      ['b', 'proposed'],
    ]);
  });

  it('keeps only the most recent attempts', () => {
    let s = proposed([], error('k0'), reply);
    for (let i = 1; i < SESSION_LIMIT + 5; i++) s = proposed(s, error(`k${String(i)}`), reply);
    expect(s).toHaveLength(SESSION_LIMIT);
    expect(s[0]?.key).toBe('k5');
  });
});
