import { z } from 'zod';

/**
 * Typed, versioned messages between the extension's contexts: the MAIN-world
 * page script, the isolated content script and the side panel. Every receiver
 * parses with `parseMessage` and drops anything that doesn't validate: the
 * MAIN world shares the page's JavaScript realm, so what it sends is
 * untrusted (docs/adr/0029).
 *
 * Bump PROTOCOL_VERSION on any breaking change to a payload.
 */
export const PROTOCOL_NAMESPACE = 'marginalia';
export const PROTOCOL_VERSION = 1;

/**
 * The page script's own version. Chrome leaves a MAIN-world script running after the
 * extension is removed or updated, so every page message says which script sent it, and
 * replies from any other version are dropped.
 */
export const PAGE_SCRIPT = 2;
const Script = z.literal(PAGE_SCRIPT);

/** The side panel's port to a tab's content script. */
export const NOTEBOOK_PORT = 'marginalia-notebook';

const Name = z.string().max(1000);

function envelope<const T extends string, P extends z.ZodType>(type: T, payload: P) {
  return z.object({
    ns: z.literal(PROTOCOL_NAMESPACE),
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal(type),
    payload,
  });
}

/** Why the notebook can't be read, as a code the panel turns into a sentence. */
export const PageProblem = z.enum([
  /** `exposeAppInBrowser` is on but `window.jupyterapp` never appeared. */
  'no-app',
  /** The app is there but the tab shows a file list, a terminal, or a text file. */
  'no-notebook',
  /** Jupyter's objects didn't look the way this version expects. */
  'unexpected',
]);
export type PageProblem = z.infer<typeof PageProblem>;

const Code = z.string().max(500_000);
const RequestId = z.string().min(1).max(64);

/**
 * An edit the panel asks for, always after you press Apply or Undo. `expected` is what the
 * cell held when the edit was made: if it changed since, the page refuses (stale).
 */
export const EditOp = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('replace'),
    index: z.number().int().nonnegative(),
    cellId: Name.nullable(),
    expected: Code,
    source: Code,
  }),
  z.object({
    kind: z.literal('insert_before'),
    index: z.number().int().nonnegative(),
    cellId: Name.nullable(),
    source: Code,
  }),
  z.object({ kind: z.literal('delete'), cellId: Name, expected: Code }),
]);
export type EditOp = z.infer<typeof EditOp>;

const Message = z.discriminatedUnion('type', [
  /** Content script -> panel, on connect: what kind of Jupyter page this is. */
  envelope(
    'tab/jupyter',
    z.object({ appName: Name, appVersion: Name.nullable(), exposesApp: z.boolean() }),
  ),
  /** Content script -> panel, on connect: an allowed site, but not a Jupyter page. */
  envelope('tab/other', z.object({})),
  /** Page -> panel: still looking, or what stopped it. */
  envelope(
    'page/status',
    z.object({
      script: Script,
      state: z.enum(['waiting', 'unavailable']),
      problem: PageProblem.optional(),
      detail: z.string().max(500).optional(),
    }),
  ),
  /**
   * Page -> panel: the open notebook. `cells` are nbformat cells with only
   * their error outputs kept; src/core/notebook.ts validates each one.
   */
  envelope(
    'notebook/snapshot',
    z.object({
      script: Script,
      path: Name,
      kernel: z.object({ name: Name.nullable(), status: z.string().max(40).nullable() }),
      cells: z.array(z.unknown()).max(20_000),
    }),
  ),
  /** Content script -> page: a panel is open, so start (or stop) reading. */
  envelope('notebook/watch', z.object({ on: z.boolean() })),
  /** Panel -> page: select this cell and scroll it into view. */
  envelope(
    'notebook/reveal',
    z.object({ index: z.number().int().nonnegative(), cellId: Name.nullable() }),
  ),
  /** Panel -> page: make this edit. */
  envelope('notebook/apply', z.object({ requestId: RequestId, op: EditOp })),
  /** Page -> panel. `cellId` is the cell that was changed or inserted, for Undo. */
  envelope(
    'notebook/applied',
    z.object({
      script: Script,
      requestId: RequestId,
      ok: z.boolean(),
      cellId: Name.nullable().optional(),
      error: z.enum(['stale', 'gone', 'unavailable']).optional(),
      detail: z.string().max(500).optional(),
    }),
  ),
  envelope(
    'notebook/revealed',
    z.object({ script: Script, ok: z.boolean(), detail: z.string().max(500).optional() }),
  ),
]);

export type Message = z.infer<typeof Message>;
export type MessageType = Message['type'];
export type MessageOf<T extends MessageType> = Extract<Message, { type: T }>;

/** Validates an incoming message; returns null for anything malformed or foreign. */
export function parseMessage(raw: unknown): Message | null {
  const result = Message.safeParse(raw);
  return result.success ? result.data : null;
}

export function makeMessage<T extends MessageType>(
  type: T,
  payload: MessageOf<T>['payload'],
): MessageOf<T> {
  return { ns: PROTOCOL_NAMESPACE, v: PROTOCOL_VERSION, type, payload } as MessageOf<T>;
}

/** What the page script may send; the content script ignores anything else on window. */
export const FROM_PAGE: ReadonlySet<MessageType> = new Set([
  'page/status',
  'notebook/snapshot',
  'notebook/revealed',
  'notebook/applied',
]);
/** What the page script accepts. */
export const TO_PAGE: ReadonlySet<MessageType> = new Set([
  'notebook/watch',
  'notebook/reveal',
  'notebook/apply',
]);
/** What a panel may ask the page for (watching is the content script's job). */
export const FROM_PANEL: ReadonlySet<MessageType> = new Set(['notebook/reveal', 'notebook/apply']);
