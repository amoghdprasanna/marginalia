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
  it('points at the notebook line, and names the library frame that raised', () => {
    const text = stripAnsi(MATMUL_TRACEBACK.join('\n'));
    expect(locate(text)).toEqual({
      where: 'Cell In[14], line 3',
      line: 'c = evolve(a, b)',
      raisedIn: 'File ~/work/control.py:12, in evolve(h, psi)',
    });
  });

  it('has no library frame when the notebook raised it', () => {
    const text = stripAnsi(MATMUL_TRACEBACK.slice(0, 3).join('\n'));
    expect(locate(text)).toEqual({
      where: 'Cell In[14], line 3',
      line: 'c = evolve(a, b)',
      raisedIn: null,
    });
  });

  it('falls back to the last frame outside the notebook', () => {
    expect(locate('File h5py/h5f.pyx:106, in h5py.h5f.open()\nOSError: x')).toEqual({
      where: 'File h5py/h5f.pyx:106, in h5py.h5f.open()',
      line: null,
      raisedIn: null,
    });
  });

  it('gives nothing for a traceback it does not recognise', () => {
    expect(locate('KeyboardInterrupt')).toEqual({ where: null, line: null, raisedIn: null });
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
      where: 'Cell In[14], line 3',
      raisedIn: 'File ~/work/control.py:12, in evolve(h, psi)',
      source: 'x = 1',
    });
    expect(s.errors[0]?.traceback).not.toContain('\u001b');
    expect(s.cells.map((c) => c.kind)).toEqual(['markdown', 'code', 'code', 'code']);
    expect(s.cells[0]?.source).toBe('# Utilities');
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
