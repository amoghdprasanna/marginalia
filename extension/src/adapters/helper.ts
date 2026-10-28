import { z } from 'zod';

/**
 * The panel's side of the desktop helper (docs/adr/0030). Chrome starts
 * `marginalia-browser-host` when we connect and stops it when we disconnect;
 * each request carries an id and gets one reply with that id.
 */
export const HELPER_NAME = 'marginalia.browser';
export const INSTALL_COMMAND = 'marginalia-browser-host install';

/** Why the helper can't answer, in terms the panel can explain. */
export type HelperProblem =
  /** Chrome found no manifest: the helper was never installed. */
  | 'missing'
  /** The manifest names another extension id. */
  | 'forbidden'
  /** The helper started, then quit (or was stopped). */
  | 'exited'
  /** It answered with an error: no key, a rate limit... `action` says what helps. */
  | 'error';

export class HelperError extends Error {
  constructor(
    message: string,
    readonly problem: HelperProblem,
    readonly action: 'retry' | 'settings' | null = null,
  ) {
    super(message);
  }
}

/** Chrome's wording for the ways a native host can fail to connect. */
export function classify(chromeMessage: string): HelperProblem {
  const m = chromeMessage.toLowerCase();
  if (m.includes('not found')) return 'missing';
  if (m.includes('forbidden')) return 'forbidden';
  return 'exited';
}

const Hello = z.object({
  type: z.literal('hello'),
  model: z.string(),
  modelName: z.string(),
  hasKey: z.boolean(),
});
export type Hello = z.infer<typeof Hello>;

const FixKind = z.enum(['replace', 'insert_before', 'none']);
const FixReply = z.object({
  type: z.literal('fix'),
  summary: z.string(),
  explanation: z.string(),
  fix: z.object({ kind: FixKind, source: z.string() }),
  model: z.string(),
});
export type FixReply = z.infer<typeof FixReply>;

const ErrorReply = z.object({
  type: z.literal('error'),
  message: z.string(),
  action: z.enum(['retry', 'settings']).nullable().optional(),
});

/** What a fix is asked with: the notebook as text, and which cell raised. */
export interface FixRequest {
  path: string;
  kernel: string | null;
  cells: { kind: string; source: string }[];
  failing: number;
  ename: string;
  evalue: string;
  traceback: string;
}

/** The part of a runtime.Port the client uses (real ports and test fakes). */
export interface NativePort {
  postMessage(msg: unknown): void;
  disconnect(): void;
  onMessage: { addListener(cb: (msg: unknown) => void): void };
  onDisconnect: { addListener(cb: () => void): void };
}

export interface Helper {
  hello(): Promise<Hello>;
  fix(request: FixRequest): Promise<FixReply>;
  /** Stops whatever is running: the helper process ends, the next request starts a new one. */
  stop(): void;
}

/**
 * `connect` opens a port (browser.runtime.connectNative); `lastError` reads
 * browser.runtime.lastError when it closes.
 */
export function createHelper(
  connect: () => NativePort,
  lastError: () => string | undefined,
): Helper {
  let port: NativePort | null = null;
  let nextId = 1;
  const pending = new Map<
    number,
    { resolve: (v: unknown) => void; reject: (e: HelperError) => void }
  >();

  const failAll = (err: HelperError) => {
    for (const p of pending.values()) p.reject(err);
    pending.clear();
  };

  const open = (): NativePort => {
    if (port !== null) return port;
    const p = connect();
    port = p;
    p.onMessage.addListener((raw) => {
      const id = (raw as { id?: unknown } | null)?.id;
      if (typeof id !== 'number') return;
      const waiting = pending.get(id);
      if (waiting === undefined) return;
      pending.delete(id);
      const error = ErrorReply.safeParse(raw);
      if (error.success)
        waiting.reject(new HelperError(error.data.message, 'error', error.data.action ?? null));
      else waiting.resolve(raw);
    });
    p.onDisconnect.addListener(() => {
      const why = lastError() ?? 'The helper stopped.';
      if (port === p) port = null;
      failAll(new HelperError(why, classify(why)));
    });
    return p;
  };

  const request = <T>(body: Record<string, unknown>, schema: z.ZodType<T>): Promise<T> =>
    new Promise<T>((resolve, reject) => {
      const id = nextId++;
      pending.set(id, {
        resolve: (raw) => {
          const parsed = schema.safeParse(raw);
          if (parsed.success) resolve(parsed.data);
          else reject(new HelperError('The helper answered in an unexpected shape.', 'exited'));
        },
        reject,
      });
      try {
        open().postMessage({ id, ...body });
      } catch (e) {
        pending.delete(id);
        const why = e instanceof Error ? e.message : String(e);
        reject(new HelperError(why, classify(why)));
      }
    });

  return {
    hello: () => request({ type: 'hello' }, Hello),
    fix: (req) => request({ type: 'fix', request: req }, FixReply),
    stop: () => {
      const p = port;
      port = null;
      failAll(new HelperError('Stopped.', 'exited'));
      p?.disconnect();
    },
  };
}
