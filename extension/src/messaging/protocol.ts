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
  envelope(
    'notebook/revealed',
    z.object({ ok: z.boolean(), detail: z.string().max(500).optional() }),
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
]);
/** What the page script accepts. */
export const TO_PAGE: ReadonlySet<MessageType> = new Set(['notebook/watch', 'notebook/reveal']);
/** What a panel may ask the page for (watching is the content script's job). */
export const FROM_PANEL: ReadonlySet<MessageType> = new Set(['notebook/reveal']);
