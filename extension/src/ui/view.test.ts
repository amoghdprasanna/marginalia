import { describe, expect, it } from 'vitest';
import { makeMessage } from '@/src/messaging/protocol';
import { codeCell, errorOutput } from '@/src/testing/fixtures';
import { initialView, reduce, splitPath, type View } from './view';

const msg = (m: Parameters<typeof reduce>[1] & { type: 'message' }) => m;
const jupyter = (exposesApp: boolean) =>
  msg({
    type: 'message',
    message: makeMessage('tab/jupyter', {
      appName: 'Jupyter Notebook',
      appVersion: '7.6.3',
      exposesApp,
    }),
  });

describe('reduce', () => {
  it('asks for access before anything else', () => {
    expect(reduce(initialView, { type: 'tab', anyPermission: false, siteAllowed: false })).toEqual({
      kind: 'needs-permission',
    });
    expect(reduce(initialView, { type: 'tab', anyPermission: true, siteAllowed: false })).toEqual({
      kind: 'other-site',
    });
    expect(reduce(initialView, { type: 'tab', anyPermission: true, siteAllowed: true })).toEqual({
      kind: 'checking',
    });
  });

  it('says to reload when an allowed tab never answers', () => {
    expect(reduce(initialView, { type: 'connect-failed' })).toEqual({ kind: 'unreachable' });
  });

  it('asks for the server setting, and keeps asking while the page waits', () => {
    const v = reduce(initialView, jupyter(false));
    expect(v).toEqual({ kind: 'needs-setting', appName: 'Jupyter Notebook' });
    const waited = reduce(
      v,
      msg({
        type: 'message',
        message: makeMessage('page/status', { state: 'unavailable', problem: 'no-app' }),
      }),
    );
    expect(waited).toBe(v);
  });

  it('reads, then shows the errors', () => {
    let v: View = reduce(initialView, jupyter(true));
    expect(v.kind).toBe('reading');
    v = reduce(
      v,
      msg({
        type: 'message',
        message: makeMessage('notebook/snapshot', {
          path: 'work/control.ipynb',
          kernel: { name: 'Python 3', status: 'idle' },
          cells: [codeCell('a', 1), codeCell('b', 2, [errorOutput()])],
        }),
      }),
    );
    expect(v.kind === 'ready' && v.summary.errors.map((e) => e.cellId)).toEqual(['b']);
  });

  it('names what went wrong', () => {
    const v = reduce(
      initialView,
      msg({
        type: 'message',
        message: makeMessage('page/status', {
          state: 'unavailable',
          problem: 'unexpected',
          detail: 'boom',
        }),
      }),
    );
    expect(v).toEqual({ kind: 'problem', problem: 'unexpected', detail: 'boom' });
    expect(
      reduce(initialView, msg({ type: 'message', message: makeMessage('tab/other', {}) })),
    ).toEqual({ kind: 'not-jupyter' });
  });
});

describe('splitPath', () => {
  it('splits the folder off', () => {
    expect(splitPath('a/b/c.ipynb')).toEqual({ name: 'c.ipynb', folder: 'a/b' });
    expect(splitPath('c.ipynb')).toEqual({ name: 'c.ipynb', folder: null });
  });
});
