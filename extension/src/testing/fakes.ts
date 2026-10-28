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

/** The objects window.jupyterapp leads to, shaped like Notebook 7's, with an editable shared model. */
export function fakeApp(cells: Record<string, unknown>[], path = 'work/control.ipynb') {
  let added = 0;
  const makeModel = (json: Record<string, unknown>) => {
    const state = {
      json: structuredClone(json),
      source: typeof json.source === 'string' ? json.source : '',
    };
    return {
      id: json.id,
      toJSON: () => ({ ...structuredClone(state.json), source: state.source }),
      sharedModel: {
        getSource: () => state.source,
        setSource: (s: string) => {
          state.source = s;
        },
      },
    };
  };
  const models = cells.map(makeModel);
  const cellList = {
    get length() {
      return models.length;
    },
    get: (i: number) => models[i],
  };
  const notebook = {
    model: {
      cells: cellList,
      sharedModel: {
        insertCell(index: number, cell: { cell_type: 'code'; source: string }) {
          const id = `added-${String(++added)}`;
          const m = makeModel({ ...cell, id, outputs: [], metadata: {}, execution_count: null });
          models.splice(index, 0, m);
          return { id };
        },
        deleteCell(index: number) {
          models.splice(index, 1);
        },
      },
    },
    activeCellIndex: 0,
    get widgets() {
      return models.map((m) => ({ cell: m }));
    },
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
  const sources = () => models.map((m) => m.sharedModel.getSource());
  return { app: { shell: { currentWidget: panel as unknown } }, panel, notebook, sources };
}
