import { summarize, type NotebookSummary } from '@/src/core/notebook';
import type { Message, PageProblem } from '@/src/messaging/protocol';

/**
 * What the side panel shows, one state at a time (docs/design.md, "Always
 * say what is happening"). `reduce` is pure so every state is tested
 * without Chrome.
 */
export type View =
  | { kind: 'checking' }
  /** You haven't allowed any site yet. */
  | { kind: 'needs-permission' }
  /** The active tab is a site you haven't allowed (or a chrome:// page). */
  | { kind: 'other-site' }
  /** An allowed site, but nothing answered: the tab was open before the scripts were. */
  | { kind: 'unreachable' }
  | { kind: 'not-jupyter' }
  | { kind: 'needs-setting'; appName: string }
  | { kind: 'reading'; appName: string }
  | { kind: 'problem'; problem: PageProblem; detail: string | null }
  | {
      kind: 'ready';
      path: string;
      kernel: { name: string | null; status: string | null };
      summary: NotebookSummary;
    };

export type ViewEvent =
  /** Which tab the panel follows, and whether Chrome lets us see its address (only on allowed sites). */
  | { type: 'tab'; anyPermission: boolean; siteAllowed: boolean }
  | { type: 'connect-failed' }
  | { type: 'message'; message: Message };

export const initialView: View = { kind: 'checking' };

export function reduce(view: View, event: ViewEvent): View {
  switch (event.type) {
    case 'tab':
      if (!event.anyPermission) return { kind: 'needs-permission' };
      if (!event.siteAllowed) return { kind: 'other-site' };
      return { kind: 'checking' };
    case 'connect-failed':
      return { kind: 'unreachable' };
    case 'message':
      return onMessage(view, event.message);
  }
}

function appNameOf(view: View): string {
  return view.kind === 'reading' || view.kind === 'needs-setting' ? view.appName : 'Jupyter';
}

function onMessage(view: View, msg: Message): View {
  switch (msg.type) {
    case 'tab/other':
      return { kind: 'not-jupyter' };
    case 'tab/jupyter':
      return msg.payload.exposesApp
        ? { kind: 'reading', appName: msg.payload.appName }
        : { kind: 'needs-setting', appName: msg.payload.appName };
    case 'page/status':
      // Without the server setting the app never appears; that card already says why.
      if (view.kind === 'needs-setting') return view;
      if (msg.payload.state === 'waiting') return { kind: 'reading', appName: appNameOf(view) };
      return {
        kind: 'problem',
        problem: msg.payload.problem ?? 'unexpected',
        detail: msg.payload.detail ?? null,
      };
    case 'notebook/snapshot':
      return {
        kind: 'ready',
        path: msg.payload.path,
        kernel: msg.payload.kernel,
        summary: summarize(msg.payload.cells),
      };
    default:
      return view;
  }
}

/** "work/jaynes_cummings_control.ipynb" -> its name and folder. */
export function splitPath(path: string): { name: string; folder: string | null } {
  const i = path.lastIndexOf('/');
  return i < 0
    ? { name: path, folder: null }
    : { name: path.slice(i + 1), folder: path.slice(0, i) };
}
