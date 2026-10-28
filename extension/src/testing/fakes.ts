import type { Transport } from '@/src/adapters/jupyter/page';
import type { Message } from '@/src/messaging/protocol';

/** Both ends of window messaging, in memory: `fromPage` is what the page script posted. */
export function fakeTransport() {
  const listeners = new Set<(raw: unknown) => void>();
  const posted: Message[] = [];
  const transport: Transport = {
    post: (msg) => posted.push(msg),
    listen: (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
  };
  return {
    transport,
    posted,
    deliver: (raw: unknown) => {
      for (const cb of listeners) cb(raw);
    },
  };
}

/** The objects window.jupyterapp leads to, shaped like Notebook 7's. */
export function fakeApp(cells: Record<string, unknown>[], path = 'work/control.ipynb') {
  const models = cells.map((json) => ({ id: json.id, toJSON: () => structuredClone(json) }));
  const notebook = {
    model: { cells: { length: models.length, get: (i: number) => models[i] } },
    activeCellIndex: 0,
    widgets: models.map((m) => ({ cell: m })),
    scrolledTo: null as unknown,
    scrollToCell(cell: unknown) {
      this.scrolledTo = cell;
    },
  };
  const panel = {
    content: notebook,
    context: { path },
    sessionContext: { kernelDisplayName: 'Python 3.13 (Conda)', kernelDisplayStatus: 'idle' },
  };
  return { app: { shell: { currentWidget: panel as unknown } }, panel, notebook };
}
