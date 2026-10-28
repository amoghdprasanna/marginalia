import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { makeMessage, PAGE_SCRIPT, type MessageOf } from '@/src/messaging/protocol';
import { codeCell, errorOutput } from '@/src/testing/fixtures';
import { fakeApp, fakeTransport } from '@/src/testing/fakes';
import { summarize } from '@/src/core/notebook';
import { claimPage, readCells, startPage } from './page';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

function setup(win: Record<string, unknown> = {}) {
  const t = fakeTransport();
  const stop = startPage({
    win: win as unknown as Window,
    transport: t.transport,
    pollMs: 100,
    giveUpMs: 1000,
  });
  const watch = (on: boolean) => t.deliver(makeMessage('notebook/watch', { on }));
  return { ...t, stop, watch, win };
}

const snapshots = (posted: { type: string }[]) =>
  posted.filter((m): m is MessageOf<'notebook/snapshot'> => m.type === 'notebook/snapshot');

describe('startPage', () => {
  it('does nothing until a panel watches', () => {
    const { posted } = setup({ jupyterapp: fakeApp([]).app });
    vi.advanceTimersByTime(1000);
    expect(posted).toEqual([]);
  });

  it('sends the open notebook with only its error outputs', () => {
    const image = { output_type: 'display_data', data: { 'image/png': 'iVBOR…' }, metadata: {} };
    const { app } = fakeApp([codeCell('a', 1, [image]), codeCell('b', 2, [errorOutput()])]);
    const { posted, watch } = setup({ jupyterapp: app });
    watch(true);
    const [snap] = snapshots(posted);
    expect(snap?.payload.path).toBe('work/control.ipynb');
    expect(snap?.payload.kernel).toEqual({ name: 'Python 3.13 (Conda)', status: 'idle' });
    const cells = snap?.payload.cells as { outputs: unknown[]; source?: unknown }[];
    expect(cells[0]?.outputs).toEqual([]);
    expect(cells[1]?.outputs).toHaveLength(1);
    expect(cells[1]?.source).toBe('x = 1');
  });

  it('sends again only when something changed', () => {
    const { app, panel } = fakeApp([codeCell('a', 1)]);
    const { posted, watch } = setup({ jupyterapp: app });
    watch(true);
    vi.advanceTimersByTime(500);
    expect(snapshots(posted)).toHaveLength(1);
    panel.sessionContext.kernelDisplayStatus = 'busy';
    vi.advanceTimersByTime(100);
    expect(snapshots(posted)).toHaveLength(2);
  });

  it('stops reading when the last panel goes', () => {
    const { app, panel } = fakeApp([codeCell('a', 1)]);
    const { posted, watch } = setup({ jupyterapp: app });
    watch(true);
    watch(false);
    panel.sessionContext.kernelDisplayStatus = 'busy';
    vi.advanceTimersByTime(1000);
    expect(snapshots(posted)).toHaveLength(1);
  });

  it('waits for window.jupyterapp, then says it never came', () => {
    const { posted, watch } = setup({});
    watch(true);
    expect(posted.at(-1)).toMatchObject({ type: 'page/status', payload: { state: 'waiting' } });
    vi.advanceTimersByTime(1100);
    expect(posted.at(-1)).toMatchObject({
      type: 'page/status',
      payload: { state: 'unavailable', problem: 'no-app' },
    });
  });

  it('picks up the app when it appears late', () => {
    const win: Record<string, unknown> = {};
    const { posted, watch } = setup(win);
    watch(true);
    win.jupyterapp = fakeApp([codeCell('a', 1)]).app;
    vi.advanceTimersByTime(100);
    expect(snapshots(posted)).toHaveLength(1);
  });

  it('says when the tab shows something other than a notebook', () => {
    const { posted, watch } = setup({
      jupyterapp: { shell: { currentWidget: { title: 'Files' } } },
    });
    watch(true);
    expect(posted.at(-1)).toMatchObject({ payload: { problem: 'no-notebook' } });
  });

  it('reports a Jupyter that throws instead of throwing into the page', () => {
    const cells = {
      length: 1,
      get: () => ({
        toJSON: () => {
          throw new Error('model disposed');
        },
      }),
    };
    const panel = {
      content: { model: { cells }, activeCellIndex: 0 },
      context: { path: 'x.ipynb' },
    };
    const { posted, watch } = setup({ jupyterapp: { shell: { currentWidget: panel } } });
    watch(true);
    expect(posted.at(-1)).toMatchObject({
      payload: { state: 'unavailable', problem: 'unexpected', detail: 'model disposed' },
    });
  });

  it('ignores messages that are not for the page', () => {
    const { posted, deliver } = setup({ jupyterapp: fakeApp([]).app });
    deliver({ ns: 'marginalia', v: 1, type: 'notebook/watch', payload: { on: 'yes' } });
    deliver(makeMessage('tab/other', {}));
    expect(posted).toEqual([]);
  });
});

describe('reveal', () => {
  it('selects the cell by id even after cells moved', () => {
    const { app, notebook } = fakeApp([codeCell('a', 1), codeCell('b', 2), codeCell('c', 3)]);
    const { posted, deliver } = setup({ jupyterapp: app });
    deliver(makeMessage('notebook/reveal', { index: 0, cellId: 'c' }));
    expect(notebook.activeCellIndex).toBe(2);
    expect(notebook.scrolledTo).toEqual(notebook.widgets[2]);
    expect(posted.at(-1)).toMatchObject({ type: 'notebook/revealed', payload: { ok: true } });
  });

  it('says so when the cell was deleted', () => {
    const { app } = fakeApp([codeCell('a', 1)]);
    const { posted, deliver } = setup({ jupyterapp: app });
    deliver(makeMessage('notebook/reveal', { index: 4, cellId: 'gone' }));
    expect(posted.at(-1)).toMatchObject({
      payload: { ok: false, detail: 'That cell was deleted.' },
    });
  });
});

describe('readCells', () => {
  it('produces cells the core reads: the contract between the two halves', () => {
    const { notebook } = fakeApp([codeCell('a', 1), codeCell('b', 2, [errorOutput()])]);
    const s = summarize(readCells(notebook.model.cells));
    expect(s.codeCellCount).toBe(2);
    expect(s.errors.map((e) => e.cellId)).toEqual(['b']);
  });

  it('keeps a placeholder for a cell that would not serialise, so positions stay right', () => {
    const cells = {
      length: 2,
      get: (i: number) => (i === 0 ? { toJSON: () => 'odd' } : { toJSON: () => codeCell('b', 1) }),
    };
    const out = readCells(cells);
    expect(out[0]).toBeNull();
    expect(out[1]).toMatchObject({ id: 'b' });
  });
});

describe('apply', () => {
  const applied = (posted: { type: string }[]) =>
    posted.filter((m): m is MessageOf<'notebook/applied'> => m.type === 'notebook/applied').at(-1)
      ?.payload;

  it('replaces a cell when it still holds what Claude saw', () => {
    const { app, sources } = fakeApp([codeCell('a', 1), codeCell('b', 2)]);
    const { posted, deliver } = setup({ jupyterapp: app });
    deliver(
      makeMessage('notebook/apply', {
        requestId: 'r1',
        op: { kind: 'replace', index: 1, cellId: 'b', expected: 'x = 1', source: 'x = 2' },
      }),
    );
    expect(sources()).toEqual(['x = 1', 'x = 2']);
    expect(applied(posted)).toEqual({
      script: PAGE_SCRIPT,
      requestId: 'r1',
      ok: true,
      cellId: 'b',
    });
  });

  it('refuses a stale edit and leaves the cell alone', () => {
    const { app, sources } = fakeApp([codeCell('a', 1)]);
    const { posted, deliver } = setup({ jupyterapp: app });
    deliver(
      makeMessage('notebook/apply', {
        requestId: 'r2',
        op: { kind: 'replace', index: 0, cellId: 'a', expected: 'something else', source: 'boom' },
      }),
    );
    expect(sources()).toEqual(['x = 1']);
    expect(applied(posted)).toMatchObject({ ok: false, error: 'stale' });
  });

  it('inserts a cell before the failing one, and deleting it undoes that', () => {
    const { app, sources, notebook } = fakeApp([codeCell('a', 1), codeCell('b', 2)]);
    const { posted, deliver } = setup({ jupyterapp: app });
    deliver(
      makeMessage('notebook/apply', {
        requestId: 'r3',
        op: { kind: 'insert_before', index: 1, cellId: 'b', source: '%pip install qutip' },
      }),
    );
    expect(sources()).toEqual(['x = 1', '%pip install qutip', 'x = 1']);
    expect(notebook.activeCellIndex).toBe(1);
    const added = applied(posted)?.cellId;
    expect(added).toBe('added-1');
    deliver(
      makeMessage('notebook/apply', {
        requestId: 'r4',
        op: { kind: 'delete', cellId: added ?? '', expected: '%pip install qutip' },
      }),
    );
    expect(sources()).toEqual(['x = 1', 'x = 1']);
  });

  it('finds the cell by id after cells moved, and says when it is gone', () => {
    const { app, sources } = fakeApp([codeCell('a', 1), codeCell('b', 2)]);
    const { posted, deliver } = setup({ jupyterapp: app });
    deliver(
      makeMessage('notebook/apply', {
        requestId: 'r5',
        op: { kind: 'replace', index: 0, cellId: 'b', expected: 'x = 1', source: 'moved' },
      }),
    );
    expect(sources()).toEqual(['x = 1', 'moved']);
    deliver(
      makeMessage('notebook/apply', {
        requestId: 'r6',
        op: { kind: 'replace', index: 0, cellId: 'zzz', expected: 'x', source: 'y' },
      }),
    );
    expect(applied(posted)).toMatchObject({ ok: false, error: 'gone' });
  });
});

describe('claimPage', () => {
  it('stops the script an earlier install left running, then starts', () => {
    const win = {} as unknown as Window;
    const log: string[] = [];
    claimPage(win, () => {
      log.push('start 1');
      return () => log.push('stop 1');
    });
    claimPage(win, () => {
      log.push('start 2');
      return () => log.push('stop 2');
    });
    expect(log).toEqual(['start 1', 'stop 1', 'start 2']);
  });

  it("starts beside the first version, whose marker can't be stopped", () => {
    const win = { [Symbol.for('marginalia.page')]: true } as unknown as Window;
    let started = false;
    claimPage(win, () => {
      started = true;
      return () => undefined;
    });
    expect(started).toBe(true);
  });
});
