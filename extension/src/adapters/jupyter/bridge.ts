import type { JupyterPage } from '@/src/core/access';
import {
  FROM_PAGE,
  FROM_PANEL,
  makeMessage,
  parseMessage,
  type Message,
} from '@/src/messaging/protocol';
import type { Transport } from './page';

/** The part of a runtime Port the bridge uses (real ports and test fakes). */
export interface PortLike {
  postMessage(msg: unknown): void;
  onMessage: { addListener(cb: (msg: unknown) => void): void };
  onDisconnect: { addListener(cb: () => void): void };
}

/**
 * Isolated-world relay between the page script (window messages) and side
 * panels (runtime ports), validating both ways (docs/adr/0029). The page only
 * reads while at least one panel is connected, so a closed panel costs nothing.
 */
export function startBridge(opts: { page: Transport; jupyter: JupyterPage }): {
  connect(port: PortLike): void;
  stop(): void;
} {
  const ports = new Set<PortLike>();
  let lastStatus: Message | null = null;
  let lastSnapshot: Message | null = null;

  const stopListening = opts.page.listen((raw) => {
    const msg = parseMessage(raw);
    if (msg === null || !FROM_PAGE.has(msg.type)) return;
    if (msg.type === 'page/status') {
      lastStatus = msg;
      lastSnapshot = null;
    }
    if (msg.type === 'notebook/snapshot') {
      lastSnapshot = msg;
      lastStatus = null;
    }
    for (const p of ports) p.postMessage(msg);
  });

  return {
    connect(port) {
      ports.add(port);
      port.postMessage(makeMessage('tab/jupyter', opts.jupyter));
      if (lastStatus) port.postMessage(lastStatus);
      if (lastSnapshot) port.postMessage(lastSnapshot);
      if (ports.size === 1) opts.page.post(makeMessage('notebook/watch', { on: true }));
      port.onDisconnect.addListener(() => {
        ports.delete(port);
        if (ports.size === 0) opts.page.post(makeMessage('notebook/watch', { on: false }));
      });
      port.onMessage.addListener((raw) => {
        const msg = parseMessage(raw);
        if (msg !== null && FROM_PANEL.has(msg.type)) opts.page.post(msg);
      });
    },
    stop() {
      stopListening();
      ports.clear();
    },
  };
}
