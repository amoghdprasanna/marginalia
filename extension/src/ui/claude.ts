import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { browser } from 'wxt/browser';
import {
  type ModelChoice,
  createHelper,
  HELPER_NAME,
  HelperError,
  type FixRequest,
  type HelperProblem,
} from '@/src/adapters/helper';
import type { CellError, NotebookSummary } from '@/src/core/notebook';
import type { Notebook } from './connection';
import { editFor, fixKey, proposalFor, undoFor, type FixState } from './fixes';

const MODEL_KEY = 'fixModel';

/** Whether Claude can be asked, as the status bar says it. */
export type ClaudeStatus =
  | { kind: 'checking' }
  | {
      kind: 'ready';
      modelName: string;
      defaultModel: string;
      models: ModelChoice[];
      hasKey: boolean;
    }
  | { kind: 'unavailable'; problem: HelperProblem; message: string };

export interface Claude {
  status: ClaudeStatus;
  /** The model fixes use: your pick in the panel, else Marginalia's setting. */
  model: string | null;
  setModel: (id: string) => void;
  fixes: Readonly<Record<string, FixState>>;
  /** Goes up by one each time a fix is applied: Ket hops. */
  landed: number;
  /** Checks the helper again (after you install it). */
  recheck: () => void;
  ask: (error: CellError, notebook: NotebookContext) => void;
  stop: (key: string) => void;
  apply: (key: string) => void;
  undo: (key: string) => void;
  dismiss: (key: string) => void;
}

export interface NotebookContext {
  path: string;
  kernel: string | null;
  summary: NotebookSummary;
}

export function fixRequest(
  error: CellError,
  nb: NotebookContext,
  model: string | null,
): FixRequest {
  return {
    ...(model !== null ? { model } : {}),
    path: nb.path,
    kernel: nb.kernel,
    cells: nb.summary.cells,
    failing: error.index,
    ename: error.ename,
    evalue: error.evalue,
    traceback: error.traceback,
  };
}

function failure(e: unknown): FixState {
  if (e instanceof HelperError)
    return { kind: 'failed', message: e.message, problem: e.problem, action: e.action };
  return { kind: 'failed', message: String(e), problem: 'exited', action: 'retry' };
}

/**
 * Talks to Claude through Marginalia's desktop helper (docs/adr/0030), and keeps each
 * error's fix: asking, the proposal, applied (with its undo), or what went wrong.
 */
export function useClaude(nb: Notebook): Claude {
  const helper = useMemo(
    () =>
      createHelper(
        () => browser.runtime.connectNative(HELPER_NAME),
        () => browser.runtime.lastError?.message,
      ),
    [],
  );
  const [status, setStatus] = useState<ClaudeStatus>({ kind: 'checking' });
  const [fixes, setFixes] = useState<Record<string, FixState>>({});
  const [landed, setLanded] = useState(0);
  // Apply and Undo read the latest state when clicked, not the state they were created with.
  const fixesRef = useRef(fixes);
  useEffect(() => {
    fixesRef.current = fixes;
  }, [fixes]);
  const stopping = useRef(new Set<string>());
  const [picked, setPicked] = useState<string | null>(null);

  // Your pick is remembered in this browser; Marginalia's own setting stays as it is.
  useEffect(() => {
    void browser.storage.local.get(MODEL_KEY).then((stored) => {
      const value: unknown = stored[MODEL_KEY];
      if (typeof value === 'string') setPicked(value);
    });
  }, []);
  const setModel = useCallback((id: string) => {
    setPicked(id);
    void browser.storage.local.set({ [MODEL_KEY]: id });
  }, []);
  const model =
    status.kind !== 'ready'
      ? null
      : picked !== null && status.models.some((m) => m.id === picked)
        ? picked
        : status.defaultModel;
  const modelRef = useRef(model);
  useEffect(() => {
    modelRef.current = model;
  }, [model]);

  const set = useCallback((key: string, state: FixState) => {
    setFixes((all) => ({ ...all, [key]: state }));
  }, []);

  const probe = useCallback(() => {
    helper.hello().then(
      (h) => {
        setStatus({
          kind: 'ready',
          modelName: h.modelName,
          defaultModel: h.model,
          models: h.models,
          hasKey: h.hasKey,
        });
      },
      (e: unknown) => {
        const err = e instanceof HelperError ? e : new HelperError(String(e), 'exited');
        setStatus({ kind: 'unavailable', problem: err.problem, message: err.message });
      },
    );
  }, [helper]);

  const recheck = useCallback(() => {
    setStatus({ kind: 'checking' });
    probe();
  }, [probe]);

  useEffect(() => {
    probe();
    return () => {
      helper.stop();
    };
  }, [helper, probe]);

  const ask = useCallback(
    (error: CellError, context: NotebookContext) => {
      const key = fixKey(error);
      set(key, { kind: 'asking', since: Date.now() });
      helper.fix(fixRequest(error, context, modelRef.current)).then(
        (reply) => {
          set(key, { kind: 'proposed', proposal: proposalFor(error, reply) });
        },
        (e: unknown) => {
          if (stopping.current.delete(key)) {
            set(key, { kind: 'idle' });
            return;
          }
          const state = failure(e);
          set(key, state);
          // A helper that isn't installed affects every fix: the status bar says so too.
          if (
            state.kind === 'failed' &&
            (state.problem === 'missing' || state.problem === 'forbidden')
          )
            setStatus({ kind: 'unavailable', problem: state.problem, message: state.message });
        },
      );
    },
    [helper, set],
  );

  const stop = useCallback(
    (key: string) => {
      stopping.current.add(key);
      helper.stop();
    },
    [helper],
  );

  const apply = useCallback(
    (key: string) => {
      const state = fixesRef.current[key];
      if (state?.kind !== 'proposed') return;
      const op = editFor(state.proposal);
      if (op === null) return;
      set(key, { kind: 'applying', proposal: state.proposal });
      void nb.apply(op).then((applied) => {
        const undo = applied.ok ? undoFor(state.proposal, applied.cellId ?? null) : null;
        if (applied.ok && undo !== null) {
          set(key, { kind: 'applied', proposal: state.proposal, undo });
          setLanded((n) => n + 1);
        } else
          set(key, {
            kind: 'failed',
            message: applied.detail ?? 'The notebook didn’t take the change.',
            problem: applied.error ?? 'unavailable',
            action: applied.error === 'stale' ? 'retry' : null,
          });
      });
    },
    [nb, set],
  );

  const undo = useCallback(
    (key: string) => {
      const state = fixesRef.current[key];
      if (state?.kind !== 'applied') return;
      set(key, { kind: 'undoing', proposal: state.proposal, undo: state.undo });
      void nb.apply(state.undo).then((applied) => {
        if (applied.ok) set(key, { kind: 'proposed', proposal: state.proposal });
        else
          set(key, {
            kind: 'failed',
            message: applied.detail ?? 'The notebook didn’t take the undo.',
            problem: applied.error ?? 'unavailable',
            action: null,
          });
      });
    },
    [nb, set],
  );

  const dismiss = useCallback(
    (key: string) => {
      set(key, { kind: 'idle' });
    },
    [set],
  );

  return { status, model, setModel, fixes, landed, recheck, ask, stop, apply, undo, dismiss };
}
