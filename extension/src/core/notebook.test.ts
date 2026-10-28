import { describe, expect, it } from 'vitest';
import { codeCell, errorOutput, MATMUL_TRACEBACK } from '@/src/testing/fixtures';
import { locate, stripAnsi, summarize, tidy } from './notebook';

describe('stripAnsi', () => {
  it('removes the colour codes IPython writes', () => {
    expect(stripAnsi('\u001b[0;31mValueError\u001b[0m: bad')).toBe('ValueError: bad');
    expect(stripAnsi('a \u001b[38;5;241m@\u001b[39m b')).toBe('a @ b');
  });
});

describe('tidy', () => {
  it('drops the rule and the terminal padding', () => {
    const text = tidy(stripAnsi(MATMUL_TRACEBACK.join('\n')));
    expect(text.startsWith('ValueError  Traceback (most recent call last)')).toBe(true);
    expect(text).not.toMatch(/^-{10,}/m);
  });
});

describe('locate', () => {
  it('finds the last frame and the line it marked', () => {
    const text = stripAnsi(MATMUL_TRACEBACK.join('\n'));
    expect(locate(text)).toEqual({
      where: 'File ~/work/control.py:12, in evolve(h, psi)',
      line: 'return h @ psi',
    });
  });

  it('names a notebook cell frame', () => {
    const text = stripAnsi(MATMUL_TRACEBACK.slice(0, 3).join('\n'));
    expect(locate(text)).toEqual({ where: 'Cell In[14], line 3', line: 'c = evolve(a, b)' });
  });

  it('gives nothing for a traceback it does not recognise', () => {
    expect(locate('KeyboardInterrupt')).toEqual({ where: null, line: null });
  });
});

describe('summarize', () => {
  it('lists code cells whose outputs hold an error, with their position and count', () => {
    const cells = [
      { cell_type: 'markdown', id: 'm1', source: '# Utilities', metadata: {} },
      codeCell('c1', 1, [{ output_type: 'stream', name: 'stdout', text: 'ok' }]),
      codeCell('c2', 14, [errorOutput('ValueError', 'matmul: mismatch')]),
      codeCell('c3', null),
    ];
    const s = summarize(cells);
    expect(s.cellCount).toBe(4);
    expect(s.codeCellCount).toBe(3);
    expect(s.errors).toHaveLength(1);
    expect(s.errors[0]).toMatchObject({
      index: 2,
      cellId: 'c2',
      executionCount: 14,
      ename: 'ValueError',
      evalue: 'matmul: mismatch',
      where: 'File ~/work/control.py:12, in evolve(h, psi)',
    });
    expect(s.errors[0]?.traceback).not.toContain('\u001b');
  });

  it('skips what is not a cell instead of failing', () => {
    const s = summarize([null, 42, { cell_type: 'code' }, codeCell('ok', 2, [errorOutput()])]);
    expect(s.cellCount).toBe(4);
    expect(s.errors.map((e) => e.index)).toEqual([3]);
  });

  it('ignores a malformed error output', () => {
    const s = summarize([codeCell('a', 1, [{ output_type: 'error', ename: 'X' }])]);
    expect(s.errors).toEqual([]);
  });

  it('reads old notebooks without cell ids', () => {
    const cell = { cell_type: 'code', source: [], outputs: [errorOutput()], execution_count: 3 };
    expect(summarize([cell]).errors[0]?.cellId).toBeNull();
  });
});
