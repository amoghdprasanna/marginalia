import { describe, expect, it } from 'vitest';
import { diffLines, hunks } from './diff';

describe('diffLines', () => {
  it('marks the changed line and keeps the rest', () => {
    expect(diffLines('a\nb\nc', 'a\nB\nc')).toEqual([
      { kind: 'same', text: 'a' },
      { kind: 'remove', text: 'b' },
      { kind: 'add', text: 'B' },
      { kind: 'same', text: 'c' },
    ]);
  });

  it('handles an empty side', () => {
    expect(diffLines('', '%pip install qutip')).toEqual([
      { kind: 'add', text: '%pip install qutip' },
    ]);
    expect(diffLines('x', '')).toEqual([{ kind: 'remove', text: 'x' }]);
  });
});

describe('hunks', () => {
  it('folds unchanged lines far from any change', () => {
    const before = Array.from({ length: 12 }, (_, i) => `line${String(i)}`).join('\n');
    const after = before.replace('line6', 'LINE6');
    const h = hunks(diffLines(before, after), 1);
    expect(h[0]).toEqual({ kind: 'skip', count: 5 });
    expect(h.filter((l) => l.kind !== 'skip').map((l) => ('text' in l ? l.text : ''))).toEqual([
      'line5',
      'line6',
      'LINE6',
      'line7',
    ]);
    expect(h.at(-1)).toEqual({ kind: 'skip', count: 4 });
  });
});
