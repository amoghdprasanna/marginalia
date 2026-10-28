import { describe, expect, it } from 'vitest';
import { classify, createHelper, HelperError, type NativePort } from './helper';

function fakePort() {
  const sent: { id: number; type: string }[] = [];
  let onMessage: (m: unknown) => void = () => undefined;
  let onDisconnect: () => void = () => undefined;
  let disconnected = false;
  const port: NativePort = {
    postMessage: (m) => sent.push(m as { id: number; type: string }),
    disconnect: () => {
      disconnected = true;
    },
    onMessage: { addListener: (cb) => (onMessage = cb) },
    onDisconnect: { addListener: (cb) => (onDisconnect = cb) },
  };
  return {
    port,
    sent,
    reply: (m: unknown) => onMessage(m),
    drop: () => onDisconnect(),
    get disconnected() {
      return disconnected;
    },
  };
}

const request = {
  path: 'x.ipynb',
  kernel: null,
  cells: [{ kind: 'code', source: 'import qutip' }],
  failing: 0,
  ename: 'ModuleNotFoundError',
  evalue: "No module named 'qutip'",
  traceback: '',
};

describe('classify', () => {
  it("reads Chrome's wording", () => {
    expect(classify('Specified native messaging host not found.')).toBe('missing');
    expect(classify('Access to the specified native messaging host is forbidden.')).toBe(
      'forbidden',
    );
    expect(classify('Native host has exited.')).toBe('exited');
  });
});

describe('createHelper', () => {
  it('matches replies to requests by id, over one port', async () => {
    const f = fakePort();
    let opened = 0;
    const helper = createHelper(
      () => (opened++, f.port),
      () => undefined,
    );
    const hello = helper.hello();
    const fix = helper.fix(request);
    expect(f.sent.map((m) => m.type)).toEqual(['hello', 'fix']);
    expect(opened).toBe(1);
    f.reply({
      id: f.sent[1]?.id,
      type: 'fix',
      summary: 's',
      explanation: 'e',
      fix: { kind: 'insert_before', source: '%pip install qutip' },
      model: 'claude-haiku-5-5',
    });
    f.reply({
      id: f.sent[0]?.id,
      type: 'hello',
      model: 'm',
      modelName: 'Claude Haiku 5.5',
      hasKey: true,
    });
    await expect(fix).resolves.toMatchObject({ fix: { kind: 'insert_before' } });
    await expect(hello).resolves.toMatchObject({ modelName: 'Claude Haiku 5.5' });
  });

  it("passes the helper's own error on, with what would help", async () => {
    const f = fakePort();
    const helper = createHelper(
      () => f.port,
      () => undefined,
    );
    const fix = helper.fix(request);
    f.reply({
      id: f.sent[0]?.id,
      type: 'error',
      message: 'Your API key was rejected.',
      action: 'settings',
    });
    await expect(fix).rejects.toMatchObject({ problem: 'error', action: 'settings' });
  });

  it('fails every waiting request when Chrome drops the port, and reconnects next time', async () => {
    const first = fakePort();
    const second = fakePort();
    const ports = [first.port, second.port];
    const helper = createHelper(
      () => ports.shift() ?? second.port,
      () => 'Specified native messaging host not found.',
    );
    const hello = helper.hello();
    first.drop();
    await expect(hello).rejects.toBeInstanceOf(HelperError);
    await expect(hello).rejects.toMatchObject({ problem: 'missing' });
    void helper.hello().catch(() => undefined);
    expect(second.sent).toHaveLength(1);
  });

  it('stop ends the process and fails what was waiting', async () => {
    const f = fakePort();
    const helper = createHelper(
      () => f.port,
      () => undefined,
    );
    const fix = helper.fix(request);
    helper.stop();
    await expect(fix).rejects.toMatchObject({ problem: 'exited' });
    expect(f.disconnected).toBe(true);
  });

  it('rejects a reply that does not have the right shape', async () => {
    const f = fakePort();
    const helper = createHelper(
      () => f.port,
      () => undefined,
    );
    const hello = helper.hello();
    f.reply({ id: f.sent[0]?.id, type: 'hello' });
    await expect(hello).rejects.toBeInstanceOf(HelperError);
  });
});
