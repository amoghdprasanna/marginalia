import { describe, expect, it } from 'vitest';
import { makeMessage, parseMessage } from './protocol';

describe('parseMessage', () => {
  it('accepts what makeMessage builds', () => {
    const msg = makeMessage('notebook/reveal', { index: 3, cellId: 'abc' });
    expect(parseMessage(msg)).toEqual(msg);
  });

  it('drops foreign, old and malformed messages', () => {
    expect(
      parseMessage({ type: 'notebook/reveal', payload: { index: 3, cellId: null } }),
    ).toBeNull();
    expect(parseMessage({ ns: 'marginalia', v: 0, type: 'tab/other', payload: {} })).toBeNull();
    expect(parseMessage({ ns: 'lemma', v: 1, type: 'tab/other', payload: {} })).toBeNull();
    expect(parseMessage(makeMessage('notebook/reveal', { index: -1, cellId: null }))).toBeNull();
    expect(parseMessage('hello')).toBeNull();
    // An old page script's snapshot (no script version) is dropped, so it can't mix with ours.
    expect(
      parseMessage({
        ns: 'marginalia',
        v: 1,
        type: 'notebook/snapshot',
        payload: { path: 'x', kernel: { name: null, status: null }, cells: [] },
      }),
    ).toBeNull();
  });
});
