import {
  makeMessage,
  parseMessage,
  TO_PAGE,
  type Message,
  type MessageOf,
  type PageProblem,
} from '@/src/messaging/protocol';

/**
 * Runs in the page's MAIN world (docs/adr/0029). Reads the open notebook
 * through `window.jupyterapp`, which Jupyter sets when the server has
 * `expose_app_in_browser`. Jupyter is code we don't control, so every object
 * is duck-typed and every call is guarded: a surprise becomes a status the
 * panel can explain, never an exception in the page.
 */
export interface Transport {
  post(msg: Message): void;
  listen(cb: (raw: unknown) => void): () => void;
}

export function windowTransport(win: Window): Transport {
  return {
    post: (msg) => {
      win.postMessage(msg, win.location.origin);
    },
    listen: (cb) => {
      const handler = (e: MessageEvent) => {
        if (e.source === win && e.origin === win.location.origin) cb(e.data);
      };
      win.addEventListener('message', handler);
      return () => {
        win.removeEventListener('message', handler);
      };
    },
  };
}

// The shapes we rely on, from @jupyterlab/notebook 4 and @jupyter-notebook/application 7.
interface SharedCell {
  getSource(): string;
  setSource(source: string): void;
}
interface CellModel {
  id?: unknown;
  toJSON(): unknown;
  sharedModel?: SharedCell;
}
interface SharedNotebook {
  insertCell(index: number, cell: { cell_type: 'code'; source: string }): { id?: unknown };
  deleteCell(index: number): void;
}
interface CellList {
  length: number;
  get(index: number): CellModel | undefined;
}
interface NotebookWidget {
  model: { cells: CellList; sharedModel?: SharedNotebook } | null;
  activeCellIndex: number;
  widgets?: readonly unknown[];
  scrollToCell?(cell: unknown, alignment?: string): Promise<void> | void;
  scrollToItem?(index: number, alignment?: string): Promise<void> | void;
}
interface NotebookPanel {
  content: NotebookWidget;
  context: { path: string };
  sessionContext?: { kernelDisplayName?: unknown; kernelDisplayStatus?: unknown };
}
interface App {
  shell: { currentWidget: unknown };
  restored?: Promise<unknown>;
}

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null;

function asApp(v: unknown): App | null {
  return isObject(v) && isObject(v.shell) ? (v as unknown as App) : null;
}

function asNotebookPanel(w: unknown): NotebookPanel | null {
  if (!isObject(w) || !isObject(w.content) || !isObject(w.context)) return null;
  const model = w.content.model;
  const cells = isObject(model) ? model.cells : null;
  if (!isObject(cells) || typeof cells.length !== 'number' || typeof cells.get !== 'function')
    return null;
  if (typeof w.context.path !== 'string') return null;
  return w as unknown as NotebookPanel;
}

const str = (v: unknown): string | null => (typeof v === 'string' && v !== '' ? v : null);

/** nbformat cells with only their error outputs: images and prints stay in the page; sources travel, for fixes. */
export function readCells(cells: CellList): unknown[] {
  const out: unknown[] = [];
  for (let i = 0; i < cells.length; i++) {
    const json = cells.get(i)?.toJSON();
    if (!isObject(json)) {
      out.push(null);
      continue;
    }
    const { attachments: _attachments, ...rest } = json;
    if (Array.isArray(rest.outputs))
      rest.outputs = rest.outputs.filter((o) => isObject(o) && o.output_type === 'error');
    out.push(rest);
  }
  return out;
}

export interface PageOptions {
  win: Window;
  transport: Transport;
  pollMs?: number;
  /** How long to wait for `window.jupyterapp` before saying it isn't there. */
  giveUpMs?: number;
}

/** Starts the page script; returns a function that stops it. */
export function startPage(opts: PageOptions): () => void {
  const { win, transport } = opts;
  const pollMs = opts.pollMs ?? 1000;
  const giveUpMs = opts.giveUpMs ?? 15_000;
  const started = Date.now();

  let app: App | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  let lastSent = '';

  const send = (msg: Message) => {
    // Only what changed: the poll runs every second, the panel redraws on each message.
    const key = JSON.stringify(msg);
    if (key === lastSent) return;
    lastSent = key;
    transport.post(msg);
  };

  const status = (state: 'waiting' | 'unavailable', problem?: PageProblem, detail?: string) => {
    send(
      makeMessage('page/status', {
        state,
        ...(problem !== undefined ? { problem } : {}),
        ...(detail !== undefined ? { detail: detail.slice(0, 500) } : {}),
      }),
    );
  };

  const findApp = (): App | null => {
    if (app !== null) return app;
    const found = asApp((win as unknown as { jupyterapp?: unknown }).jupyterapp);
    if (found === null) return null;
    app = found;
    return app;
  };

  const currentPanel = (): NotebookPanel | null => {
    const a = findApp();
    return a === null ? null : asNotebookPanel(a.shell.currentWidget);
  };

  const tick = () => {
    try {
      const a = findApp();
      if (a === null) {
        if (Date.now() - started < giveUpMs) status('waiting');
        else status('unavailable', 'no-app');
        return;
      }
      const panel = currentPanel();
      if (panel === null) {
        status('unavailable', 'no-notebook');
        return;
      }
      const model = panel.content.model;
      if (model === null) {
        status('waiting');
        return;
      }
      const session = panel.sessionContext;
      send(
        makeMessage('notebook/snapshot', {
          path: panel.context.path.slice(0, 1000),
          kernel: {
            name: str(session?.kernelDisplayName)?.slice(0, 1000) ?? null,
            status: str(session?.kernelDisplayStatus)?.slice(0, 40) ?? null,
          },
          cells: readCells(model.cells),
        }),
      );
    } catch (e) {
      status('unavailable', 'unexpected', e instanceof Error ? e.message : String(e));
    }
  };

  const watch = (on: boolean) => {
    if (timer !== null) clearInterval(timer);
    timer = null;
    if (!on) return;
    lastSent = ''; // a new panel needs the current state even if nothing changed
    tick();
    timer = setInterval(tick, pollMs);
  };

  const reveal = (payload: MessageOf<'notebook/reveal'>['payload']) => {
    const done = (ok: boolean, detail?: string) => {
      transport.post(makeMessage('notebook/revealed', { ok, ...(detail ? { detail } : {}) }));
    };
    try {
      const panel = currentPanel();
      const cells = panel?.content.model?.cells;
      if (panel === null || cells === undefined) {
        done(false, 'The notebook is no longer open in this tab.');
        return;
      }
      // Cells move when you insert or delete above; the id finds the same cell.
      let index = payload.index;
      if (payload.cellId !== null && cells.get(index)?.id !== payload.cellId) {
        index = -1;
        for (let i = 0; i < cells.length; i++) if (cells.get(i)?.id === payload.cellId) index = i;
      }
      if (index < 0 || index >= cells.length) {
        done(false, 'That cell was deleted.');
        return;
      }
      const nb = panel.content;
      nb.activeCellIndex = index;
      const widget = nb.widgets?.[index];
      if (widget !== undefined && typeof nb.scrollToCell === 'function')
        void nb.scrollToCell(widget, 'center');
      else if (typeof nb.scrollToItem === 'function') void nb.scrollToItem(index, 'center');
      done(true);
    } catch (e) {
      done(false, e instanceof Error ? e.message : String(e));
    }
  };

  /** Finds a cell by id (cells move when you insert or delete above), else trusts the index. */
  const locateCell = (cells: CellList, index: number, cellId: string | null): number => {
    if (cellId === null) return index < cells.length ? index : -1;
    if (cells.get(index)?.id === cellId) return index;
    for (let i = 0; i < cells.length; i++) if (cells.get(i)?.id === cellId) return i;
    return -1;
  };

  const apply = ({ requestId, op }: MessageOf<'notebook/apply'>['payload']) => {
    const done = (
      ok: boolean,
      extra: {
        cellId?: string | null;
        error?: 'stale' | 'gone' | 'unavailable';
        detail?: string;
      } = {},
    ) => {
      transport.post(makeMessage('notebook/applied', { requestId, ok, ...extra }));
    };
    try {
      const panel = currentPanel();
      const model = panel?.content.model;
      if (panel === null || model === null || model === undefined) {
        done(false, {
          error: 'unavailable',
          detail: 'The notebook is no longer open in this tab.',
        });
        return;
      }
      const cells = model.cells;
      const at =
        op.kind === 'delete'
          ? locateCell(cells, 0, op.cellId)
          : locateCell(cells, op.index, op.cellId);
      const cell = at < 0 ? undefined : cells.get(at);
      if (cell === undefined) {
        done(false, { error: 'gone', detail: 'That cell was deleted.' });
        return;
      }
      const shared = cell.sharedModel;
      if (shared === undefined || typeof shared.getSource !== 'function') {
        done(false, {
          error: 'unavailable',
          detail: 'This Jupyter version doesn’t allow edits from Marginalia.',
        });
        return;
      }
      if (op.kind !== 'insert_before' && shared.getSource() !== op.expected) {
        done(false, { error: 'stale', detail: 'The cell changed since Claude looked at it.' });
        return;
      }
      const nb = model.sharedModel;
      if (op.kind === 'replace') {
        shared.setSource(op.source);
        done(true, { cellId: typeof cell.id === 'string' ? cell.id : null });
      } else if (op.kind === 'insert_before') {
        if (nb === undefined || typeof nb.insertCell !== 'function')
          throw new Error('no insertCell');
        const added = nb.insertCell(at, { cell_type: 'code', source: op.source });
        panel.content.activeCellIndex = at;
        done(true, { cellId: typeof added.id === 'string' ? added.id : null });
      } else {
        if (nb === undefined || typeof nb.deleteCell !== 'function')
          throw new Error('no deleteCell');
        nb.deleteCell(at);
        done(true, { cellId: null });
      }
    } catch (e) {
      done(false, { error: 'unavailable', detail: e instanceof Error ? e.message : String(e) });
    }
  };

  const stopListening = transport.listen((raw) => {
    const msg = parseMessage(raw);
    if (msg === null || !TO_PAGE.has(msg.type)) return;
    if (msg.type === 'notebook/watch') watch(msg.payload.on);
    if (msg.type === 'notebook/reveal') reveal(msg.payload);
    if (msg.type === 'notebook/apply') apply(msg.payload);
  });

  return () => {
    watch(false);
    stopListening();
  };
}
