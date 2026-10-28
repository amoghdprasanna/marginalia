import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { browser, type Browser } from 'wxt/browser';
import { allowedSites, requestLocal, requestSite } from '@/src/adapters/permissions';
import {
  makeMessage,
  NOTEBOOK_PORT,
  PAGE_SCRIPT,
  parseMessage,
  type EditOp,
  type MessageOf,
} from '@/src/messaging/protocol';
import { initialView, reduce, type View } from './view';

/**
 * `sidepanel.html?tab=<id>` pins the panel to one tab instead of following the
 * active one: the e2e tests open the panel as a page, as Lemma's do.
 */
function pinnedTab(): number | null {
  const id = Number(new URLSearchParams(location.search).get('tab'));
  return Number.isInteger(id) && id > 0 ? id : null;
}

/** A content script registered at document_idle may not be listening yet: try a few times. */
const CONNECT_TRIES = 6;
const RETRY_MS = 400;

export interface Notebook {
  view: View;
  /** Why the last "Go to cell" didn't work, until the next one. */
  revealProblem: string | null;
  /** Allows Jupyter on this computer. */
  allow: () => void;
  /** Allows one more site, by match pattern; resolves with whether you said yes. */
  addSite: (pattern: string) => Promise<boolean>;
  reload: () => void;
  reveal: (index: number, cellId: string | null) => void;
  /** Makes an edit in the notebook; resolves with the page's answer. */
  apply: (op: EditOp) => Promise<Applied>;
}

export type Applied = MessageOf<'notebook/applied'>['payload'];

/** An edit takes milliseconds; a tab that hasn't answered by then won't. */
const APPLY_TIMEOUT_MS = 6000;

const NO_ANSWER: Applied = {
  script: PAGE_SCRIPT,
  requestId: '-',
  ok: false,
  error: 'unavailable',
  detail: 'The notebook tab didn’t answer. Reload the tab, then try again.',
};

const NOT_CONNECTED: Applied = {
  script: PAGE_SCRIPT,
  requestId: '-',
  ok: false,
  error: 'unavailable',
  detail: 'Marginalia lost the tab. Wait a moment and try again.',
};

/**
 * Follows the active tab of the panel's window and talks to its content
 * script. Each connection is to one tab, so an answer can't land on another
 * (docs/adr/0029). A page that reloads drops the port; we reconnect.
 */
export function useNotebook(): Notebook {
  const [view, dispatch] = useReducer(reduce, initialView);
  const [revealProblem, setRevealProblem] = useState<string | null>(null);
  const port = useRef<Browser.runtime.Port | null>(null);
  const tabId = useRef<number | null>(null);
  const applies = useRef(new Map<string, (a: Applied) => void>());

  useEffect(() => {
    let generation = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const drop = () => {
      clearTimeout(timer);
      const p = port.current;
      port.current = null;
      p?.disconnect();
    };

    const open = (id: number, mine: number, tries: number) => {
      const p = browser.tabs.connect(id, { name: NOTEBOOK_PORT });
      let heard = false;
      port.current = p;
      p.onMessage.addListener((raw) => {
        if (mine !== generation) return;
        const message = parseMessage(raw);
        if (message === null) return;
        heard = true;
        if (message.type === 'notebook/revealed')
          setRevealProblem(message.payload.ok ? null : (message.payload.detail ?? 'Not found.'));
        else if (message.type === 'notebook/applied') {
          applies.current.get(message.payload.requestId)?.(message.payload);
          applies.current.delete(message.payload.requestId);
        } else dispatch({ type: 'message', message });
      });
      p.onDisconnect.addListener(() => {
        // Reading lastError tells Chrome we handled "Receiving end does not exist".
        const why = browser.runtime.lastError?.message;
        if (mine !== generation || port.current !== p) return;
        port.current = null;
        // An edit in flight when the tab went away: say so rather than wait forever.
        for (const resolve of applies.current.values()) resolve(NOT_CONNECTED);
        applies.current.clear();
        if (!heard && tries <= 1) {
          console.debug('Marginalia: the tab did not answer:', why ?? 'disconnected');
          dispatch({ type: 'connect-failed' });
        } else
          timer = setTimeout(() => open(id, mine, heard ? CONNECT_TRIES : tries - 1), RETRY_MS);
      });
    };

    const follow = async () => {
      const mine = ++generation;
      drop();
      const pinned = pinnedTab();
      const [tab] =
        pinned !== null
          ? [await browser.tabs.get(pinned)]
          : await browser.tabs.query({ active: true, currentWindow: true });
      const sites = await allowedSites();
      if (mine !== generation) return;
      tabId.current = tab?.id ?? null;
      setRevealProblem(null);
      // Chrome shows us a tab's address only on sites we may read.
      const siteAllowed = tab?.url !== undefined && /^https?:/.test(tab.url);
      dispatch({ type: 'tab', anyPermission: sites.length > 0 || siteAllowed, siteAllowed });
      if (siteAllowed && tab.id !== undefined) open(tab.id, mine, CONNECT_TRIES);
    };

    const onUpdated = (id: number, change: Browser.tabs.OnUpdatedInfo) => {
      if (id === tabId.current && (change.status === 'complete' || change.url !== undefined))
        void follow();
    };
    const onActivated = () => {
      if (pinnedTab() === null) void follow();
    };
    const onPermissions = () => void follow();

    void follow();
    browser.tabs.onActivated.addListener(onActivated);
    browser.tabs.onUpdated.addListener(onUpdated);
    browser.permissions.onAdded.addListener(onPermissions);
    browser.permissions.onRemoved.addListener(onPermissions);
    return () => {
      generation++;
      drop();
      browser.tabs.onActivated.removeListener(onActivated);
      browser.tabs.onUpdated.removeListener(onUpdated);
      browser.permissions.onAdded.removeListener(onPermissions);
      browser.permissions.onRemoved.removeListener(onPermissions);
    };
  }, []);

  const allow = useCallback(() => {
    void requestLocal();
  }, []);
  const addSite = useCallback((pattern: string) => requestSite(pattern), []);
  const reload = useCallback(() => {
    if (tabId.current !== null) void browser.tabs.reload(tabId.current);
  }, []);
  const reveal = useCallback((index: number, cellId: string | null) => {
    setRevealProblem(null);
    port.current?.postMessage(makeMessage('notebook/reveal', { index, cellId }));
  }, []);

  const apply = useCallback(
    (op: EditOp) =>
      new Promise<Applied>((resolve) => {
        const p = port.current;
        if (p === null) {
          resolve(NOT_CONNECTED);
          return;
        }
        const requestId = crypto.randomUUID();
        const timer = setTimeout(() => {
          applies.current.delete(requestId);
          resolve(NO_ANSWER);
        }, APPLY_TIMEOUT_MS);
        applies.current.set(requestId, (a) => {
          clearTimeout(timer);
          resolve(a);
        });
        p.postMessage(makeMessage('notebook/apply', { requestId, op }));
      }),
    [],
  );

  return { view, revealProblem, allow, addSite, reload, reveal, apply };
}
