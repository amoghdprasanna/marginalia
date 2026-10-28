import { describe, expect, it } from 'vitest';
import { PAGE_SCRIPT, makeMessage, type Message } from '@/src/messaging/protocol';
import { fakeTransport } from '@/src/testing/fakes';
import { startBridge, type PortLike } from './bridge';

const jupyter = { appName: 'Jupyter Notebook', appVersion: '7.6.3', exposesApp: true };

function fakePort() {
  const sent: Message[] = [];
  let onMessage: (m: unknown) => void = () => undefined;
  let onDisconnect: () => void = () => undefined;
  const port: PortLike = {
    postMessage: (m) => sent.push(m as Message),
    onMessage: { addListener: (cb) => (onMessage = cb) },
    onDisconnect: { addListener: (cb) => (onDisconnect = cb) },
  };
  return { port, sent, send: (m: unknown) => onMessage(m), disconnect: () => onDisconnect() };
}

describe('startBridge', () => {
  it('greets a panel, starts watching with the first and stops with the last', () => {
    const page = fakeTransport();
    const bridge = startBridge({ page: page.transport, jupyter });
    const a = fakePort();
    const b = fakePort();
    bridge.connect(a.port);
    bridge.connect(b.port);
    expect(a.sent[0]).toEqual(makeMessage('tab/jupyter', jupyter));
    expect(page.posted.filter((m) => m.type === 'notebook/watch')).toHaveLength(1);
    a.disconnect();
    expect(page.posted.at(-1)).toEqual(makeMessage('notebook/watch', { on: true }));
    b.disconnect();
    expect(page.posted.at(-1)).toEqual(makeMessage('notebook/watch', { on: false }));
  });

  it('relays the page to panels and replays the latest to a new one', () => {
    const page = fakeTransport();
    const bridge = startBridge({ page: page.transport, jupyter });
    const a = fakePort();
    bridge.connect(a.port);
    const snap = makeMessage('notebook/snapshot', {
      script: PAGE_SCRIPT,
      path: 'x.ipynb',
      kernel: { name: null, status: null },
      cells: [],
    });
    page.deliver(snap);
    expect(a.sent.at(-1)).toEqual(snap);
    const late = fakePort();
    bridge.connect(late.port);
    expect(late.sent).toEqual([makeMessage('tab/jupyter', jupyter), snap]);
  });

  it('forwards only what a panel may ask, and drops what the page may not say', () => {
    const page = fakeTransport();
    const bridge = startBridge({ page: page.transport, jupyter });
    const a = fakePort();
    bridge.connect(a.port);
    a.send(makeMessage('notebook/watch', { on: false }));
    a.send({ type: 'notebook/reveal', payload: { index: -1 } });
    a.send(makeMessage('notebook/reveal', { index: 2, cellId: 'c' }));
    expect(page.posted.map((m) => m.type)).toEqual(['notebook/watch', 'notebook/reveal']);
    page.deliver(makeMessage('tab/other', {}));
    expect(a.sent.map((m) => m.type)).toEqual(['tab/jupyter']);
  });
});
