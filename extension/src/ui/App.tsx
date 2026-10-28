import { useEffect, useState, type ReactNode } from 'react';
import { INSTALL_COMMAND } from '@/src/adapters/helper';
import { SERVER_CONFIG_LINES } from '@/src/core/access';
import { diffLines, hunks } from '@/src/core/diff';
import type { CellError } from '@/src/core/notebook';
import { useClaude, type Claude, type ClaudeStatus, type NotebookContext } from './claude';
import { useNotebook, type Notebook } from './connection';
import { appliedText, fixKey, type FixState, type Proposal } from './fixes';
import { Icon } from './icons';
import { Ket, type Mood } from './Ket';
import { splitPath, type View } from './view';

const CONFIG_TEXT = SERVER_CONFIG_LINES.join('\n');
const CONFIG_FILE = '~/.jupyter/jupyter_server_config.py';

function moodOf(view: View, claude: Claude): Mood {
  if (Object.values(claude.fixes).some((f) => f.kind === 'asking')) return 'thinking';
  switch (view.kind) {
    case 'checking':
    case 'reading':
      return 'thinking';
    case 'needs-permission':
    case 'other-site':
    case 'not-jupyter':
      return 'asleep';
    case 'unreachable':
    case 'needs-setting':
      return 'awake';
    case 'problem':
      return view.problem === 'no-notebook' ? 'awake' : 'worried';
    case 'ready':
      if (view.summary.errors.length > 0) return 'worried';
      return view.kernel.status === 'busy' ? 'thinking' : 'happy';
  }
}

/** Seconds since `since`, ticking only while something is waiting. */
function useSeconds(since: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (since === null) return;
    const t = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => {
      window.clearInterval(t);
    };
  }, [since]);
  return since === null ? 0 : Math.max(0, Math.round((now - since) / 1000));
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="btn ghost"
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => {
            setCopied(false);
          }, 1600);
        });
      }}
    >
      <Icon name={copied ? 'check' : 'copy'} />
      {copied ? 'Copied' : label}
    </button>
  );
}

/** A file's lines: its name above, Copy beside it, lines that scroll rather than wrap. */
function CodeBlock({ file, text }: { file: string; text: string }) {
  return (
    <figure className="codeblock">
      <figcaption>
        <code>{file}</code>
        <CopyButton text={text} label="Copy" />
      </figcaption>
      <pre>{text}</pre>
    </figure>
  );
}

function Header({ view, claude }: { view: View; claude: Claude }) {
  const ready = view.kind === 'ready' ? splitPath(view.path) : null;
  return (
    <header className="header">
      <Ket mood={moodOf(view, claude)} celebrate={claude.landed} />
      <div className="header-text">
        <h1 className="brand">Marginalia</h1>
        {ready !== null ? (
          <p className="file" title={view.kind === 'ready' ? view.path : undefined}>
            <Icon name="notebook" />
            <span>{ready.name}</span>
          </p>
        ) : (
          <p className="file muted">Jupyter notebooks</p>
        )}
      </div>
    </header>
  );
}

function StatusBar({ view, claude }: { view: View; claude: Claude }) {
  let left: ReactNode = 'Looking at this tab';
  if (view.kind === 'ready') {
    const { name, status } = view.kernel;
    left = (
      <>
        <span className="dot" data-status={status ?? 'unknown'} />
        {name === null ? 'No kernel' : status === null ? name : `${name}, ${status}`}
      </>
    );
  } else if (view.kind === 'needs-setting') left = 'Needs a server setting';
  else if (view.kind === 'needs-permission') left = 'Not allowed yet';
  else if (view.kind === 'reading') left = 'Reading';
  else if (view.kind === 'not-jupyter' || view.kind === 'other-site') left = 'Nothing to read';
  return (
    <footer className="statusbar">
      <span className="status-left">{left}</span>
      <ClaudeBadge status={claude.status} />
    </footer>
  );
}

function ClaudeBadge({ status }: { status: ClaudeStatus }) {
  if (status.kind === 'checking') return <span className="badge muted">Connecting to Claude</span>;
  if (status.kind === 'unavailable')
    return (
      <span className="badge warn" title={status.message}>
        <Icon name="sparkle" />
        Claude not connected
      </span>
    );
  return (
    <span className={status.hasKey ? 'badge' : 'badge warn'}>
      <Icon name="sparkle" />
      {status.hasKey ? status.modelName : 'No Claude key'}
    </span>
  );
}

function Note({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="note">
      <h2 className="title">{title}</h2>
      {children}
    </section>
  );
}

function Diff({ proposal }: { proposal: Proposal }) {
  const { kind, source } = proposal.reply.fix;
  const lines =
    kind === 'insert_before' ? diffLines('', source) : diffLines(proposal.expected, source);
  const caption =
    kind === 'insert_before'
      ? `New cell before cell ${String(proposal.cellNumber)}`
      : `Change to cell ${String(proposal.cellNumber)}`;
  return (
    <figure className="diff">
      <figcaption>{caption}</figcaption>
      <pre>
        {hunks(lines).map((l, i) =>
          l.kind === 'skip' ? (
            <span key={i} className="diff-skip">
              {l.count} unchanged {l.count === 1 ? 'line' : 'lines'}
            </span>
          ) : (
            <span key={i} className={`diff-${l.kind}`}>
              <span className="diff-mark" aria-hidden="true">
                {l.kind === 'add' ? '+' : l.kind === 'remove' ? '−' : ' '}
              </span>
              {l.text === '' ? ' ' : l.text}
              <span className="visually-hidden">
                {l.kind === 'add' ? ' (added)' : l.kind === 'remove' ? ' (removed)' : ''}
              </span>
            </span>
          ),
        )}
      </pre>
    </figure>
  );
}

function SetupHelper({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="setup">
      <p className="fix-summary">Connect Claude on this Mac</p>
      <p className="fix-why">
        Fixes come from Marginalia on your computer, with the Claude key in its keychain, so no key
        lives in the browser. Run this once in Terminal, from the Python environment Marginalia is
        installed in:
      </p>
      <CodeBlock file="Terminal" text={INSTALL_COMMAND} />
      <div className="actions">
        <button type="button" className="btn" onClick={onRetry}>
          Try again
        </button>
      </div>
    </div>
  );
}

function FixArea({
  state,
  claude,
  fkey,
  onAsk,
}: {
  state: FixState;
  claude: Claude;
  fkey: string;
  onAsk: () => void;
}) {
  const since = state.kind === 'asking' ? state.since : null;
  const seconds = useSeconds(since);
  switch (state.kind) {
    case 'idle':
      return null;
    case 'asking':
      return (
        <div className="fix" role="status">
          <p className="working">
            <span className="pulse" aria-hidden="true" />
            Claude is reading the notebook{seconds >= 3 ? ` (${String(seconds)} s)` : '…'}
          </p>
          <div className="actions">
            <button type="button" className="btn ghost" onClick={() => claude.stop(fkey)}>
              Stop
            </button>
          </div>
        </div>
      );
    case 'proposed':
    case 'applying': {
      const { reply } = state.proposal;
      const busy = state.kind === 'applying';
      return (
        <div className="fix">
          <p className="fix-summary">{reply.summary}</p>
          <p className="fix-why">{reply.explanation}</p>
          {reply.fix.kind === 'none' ? (
            <div className="actions">
              <button type="button" className="btn" onClick={onAsk}>
                Ask again
              </button>
              <button type="button" className="btn ghost" onClick={() => claude.dismiss(fkey)}>
                Dismiss
              </button>
            </div>
          ) : (
            <>
              <Diff proposal={state.proposal} />
              <div className="actions">
                <button
                  type="button"
                  className="btn primary"
                  disabled={busy}
                  onClick={() => claude.apply(fkey)}
                >
                  {busy ? 'Applying…' : 'Apply'}
                </button>
                <button
                  type="button"
                  className="btn ghost"
                  disabled={busy}
                  onClick={() => claude.dismiss(fkey)}
                >
                  Dismiss
                </button>
              </div>
            </>
          )}
        </div>
      );
    }
    case 'applied':
    case 'undoing':
      return (
        <div className="fix done" role="status">
          <p className="applied">
            <Icon name="check" />
            {appliedText(state.proposal)}
          </p>
          <div className="actions">
            <button
              type="button"
              className="btn ghost"
              disabled={state.kind === 'undoing'}
              onClick={() => claude.undo(fkey)}
            >
              <Icon name="undo" />
              {state.kind === 'undoing' ? 'Undoing…' : 'Undo'}
            </button>
          </div>
        </div>
      );
    case 'failed':
      if (state.problem === 'missing' || state.problem === 'forbidden')
        return <SetupHelper onRetry={onAsk} />;
      return (
        <div className="fix failed" role="alert">
          <p className="fix-error">{state.message}</p>
          {state.action === 'settings' && (
            <p className="fix-why">Open Marginalia&rsquo;s Settings on this Mac, under AI model.</p>
          )}
          <div className="actions">
            {state.action !== 'settings' && (
              <button type="button" className="btn" onClick={onAsk}>
                {state.problem === 'stale' ? 'Ask again' : 'Try again'}
              </button>
            )}
            <button type="button" className="btn ghost" onClick={() => claude.dismiss(fkey)}>
              Dismiss
            </button>
          </div>
        </div>
      );
  }
}

function ErrorItem({
  error,
  context,
  nb,
  claude,
}: {
  error: CellError;
  context: NotebookContext;
  nb: Notebook;
  claude: Claude;
}) {
  const [open, setOpen] = useState(false);
  const fkey = fixKey(error);
  const state = claude.fixes[fkey] ?? { kind: 'idle' };
  const ask = () => claude.ask(error, context);
  const canAsk = state.kind === 'idle';
  const detailsId = `details-${fkey}`;
  return (
    <li className="item">
      <div className="item-head">
        <Icon name="error" className="item-icon" />
        <h3 className="item-title">{error.ename}</h3>
        <span className="chip">Cell {error.index + 1}</span>
      </div>
      {error.evalue !== '' && <p className="item-msg">{error.evalue}</p>}
      {error.where !== null && (
        <div className="item-where">
          <span>{error.where}</span>
          {error.line !== null && <code className="item-line">{error.line}</code>}
          {error.raisedIn !== null && <span className="muted">Raised in {error.raisedIn}</span>}
        </div>
      )}
      <div className="actions">
        {canAsk && (
          <button type="button" className="btn primary" onClick={ask}>
            <Icon name="sparkle" />
            Fix with Claude
          </button>
        )}
        <button
          type="button"
          className="btn ghost"
          onClick={() => nb.reveal(error.index, error.cellId)}
        >
          <Icon name="goto" />
          Go to cell
        </button>
        <button
          type="button"
          className="btn ghost disclose"
          aria-expanded={open}
          aria-controls={detailsId}
          onClick={() => {
            setOpen((o) => !o);
          }}
        >
          <Icon name="chevron" />
          Details
        </button>
      </div>
      {open && (
        <div className="details" id={detailsId}>
          <pre>{error.traceback}</pre>
          <CopyButton
            text={`${error.ename}: ${error.evalue}\n\n${error.traceback}`}
            label="Copy error"
          />
        </div>
      )}
      <FixArea state={state} claude={claude} fkey={fkey} onAsk={ask} />
    </li>
  );
}

function Body({ nb, claude }: { nb: Notebook; claude: Claude }) {
  const { view } = nb;
  switch (view.kind) {
    case 'checking':
      return <p className="muted">Looking at this tab…</p>;
    case 'needs-permission':
      return (
        <Note title="Read your notebooks">
          <p>
            Marginalia reads Jupyter notebooks on UMD&rsquo;s servers and on your own computer, and
            no other sites. Chrome asks once.
          </p>
          <div className="actions">
            <button type="button" className="btn primary" onClick={nb.allow}>
              Allow access
            </button>
          </div>
        </Note>
      );
    case 'other-site':
      return (
        <Note title="Nothing to read here">
          <p>
            Switch to a Jupyter notebook tab, on UMD&rsquo;s servers or on localhost, and Ket wakes
            up.
          </p>
        </Note>
      );
    case 'unreachable':
      return (
        <Note title="Reload to connect">
          <p>This tab was open before Marginalia could read it. Reloading it connects them.</p>
          <div className="actions">
            <button type="button" className="btn primary" onClick={nb.reload}>
              Reload tab
            </button>
          </div>
        </Note>
      );
    case 'not-jupyter':
      return (
        <Note title="This page isn’t Jupyter">
          <p>Open a notebook in this tab and Ket wakes up.</p>
        </Note>
      );
    case 'needs-setting':
      return (
        <Note title="One setting on the server">
          <p>
            {view.appName} lets an extension read a notebook only when its server allows it. Add
            these lines to this file on the server, then start Jupyter again.
          </p>
          <CodeBlock file={CONFIG_FILE} text={CONFIG_TEXT} />
          <p className="muted small">
            Restarting the kernel isn&rsquo;t enough: the server reads this file when it starts.
          </p>
        </Note>
      );
    case 'reading':
      return <p className="muted">Reading the notebook…</p>;
    case 'problem':
      if (view.problem === 'no-notebook')
        return (
          <Note title="Open a notebook">
            <p>Marginalia reads the notebook open in this tab. Open one from the file list.</p>
          </Note>
        );
      return (
        <Note
          title={
            view.problem === 'no-app'
              ? 'Jupyter didn’t share the notebook'
              : 'This Jupyter looks different'
          }
        >
          <p>
            {view.problem === 'no-app'
              ? 'The server setting is on, but the page never made the notebook available. Reload the tab; if it happens again, the server may be older than Notebook 7.'
              : 'Its notebook didn’t have the shape Marginalia expects, so reading stopped. Reloading may help.'}
          </p>
          {view.detail !== null && <p className="muted small">{view.detail}</p>}
          <div className="actions">
            <button type="button" className="btn primary" onClick={nb.reload}>
              Reload tab
            </button>
          </div>
        </Note>
      );
    case 'ready': {
      const { errors, codeCellCount } = view.summary;
      const context: NotebookContext = {
        path: view.path,
        kernel: view.kernel.name,
        summary: view.summary,
      };
      if (errors.length === 0)
        return (
          <Note title="No cell has an error">
            <p className="muted">
              {codeCellCount} code {codeCellCount === 1 ? 'cell' : 'cells'}. An error shows up here
              as soon as a cell raises one.
            </p>
          </Note>
        );
      return (
        <section>
          <h2 className="title">
            {errors.length} {errors.length === 1 ? 'cell raised an error' : 'cells raised errors'}
          </h2>
          <p className="muted small lede">
            Claude proposes a change; nothing in the notebook changes until you press Apply.
          </p>
          {nb.revealProblem !== null && (
            <p className="reveal-problem" role="status">
              {nb.revealProblem}
            </p>
          )}
          <ul className="items">
            {errors.map((e) => (
              <ErrorItem key={fixKey(e)} error={e} context={context} nb={nb} claude={claude} />
            ))}
          </ul>
        </section>
      );
    }
  }
}

export function App() {
  const nb = useNotebook();
  const claude = useClaude(nb);
  return (
    <div className="app">
      <Header view={nb.view} claude={claude} />
      <main className="main">
        <Body nb={nb} claude={claude} />
      </main>
      <StatusBar view={nb.view} claude={claude} />
    </div>
  );
}
