import { useEffect, useState, type ReactNode } from 'react';
import { browser } from 'wxt/browser';
import { CHECK_COMMAND, EXPECTED_ID, INSTALL_COMMAND } from '@/src/adapters/helper';
import { SERVER_CONFIG_LINES } from '@/src/core/access';
import { diffLines, hunks } from '@/src/core/diff';
import type { CellError } from '@/src/core/notebook';
import { sitePattern } from '@/src/core/site';
import { useClaude, type Claude, type NotebookContext } from './claude';
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
    case 'ready': {
      const open = view.summary.errors.filter((e) => claude.fixes[fixKey(e)]?.kind !== 'applied');
      if (open.length > 0) return 'worried';
      return view.kernel.status === 'busy' ? 'thinking' : 'happy';
    }
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
      className="btn quiet"
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
  const file = view.kind === 'ready' ? splitPath(view.path) : null;
  return (
    <header className="header">
      <Ket mood={moodOf(view, claude)} size={72} celebrate={claude.landed} />
      <div className="header-text">
        {file !== null ? (
          <>
            <h1 className="notebook" title={view.kind === 'ready' ? view.path : undefined}>
              {file.name}
            </h1>
            {file.folder !== null && <p className="folder">{file.folder}</p>}
          </>
        ) : (
          <>
            <h1 className="notebook">Marginalia</h1>
            <p className="folder">Reads your Jupyter notebook and fixes errors with Claude.</p>
          </>
        )}
      </div>
    </header>
  );
}

function ModelMenu({ claude }: { claude: Claude }) {
  const { status, model } = claude;
  if (status.kind === 'checking') return <span className="status-claude muted">Connecting…</span>;
  if (status.kind === 'unavailable')
    return (
      <span className="status-claude warn" title={status.message}>
        <Icon name="sparkle" />
        Claude not connected
      </span>
    );
  if (!status.hasKey)
    return (
      <span className="status-claude warn">
        <Icon name="sparkle" />
        No Claude key
      </span>
    );
  if (status.models.length === 0)
    return (
      <span className="status-claude">
        <Icon name="sparkle" />
        {status.modelName}
      </span>
    );
  const note = status.models.find((m) => m.id === model)?.note;
  return (
    <label className="status-claude" title={note}>
      <Icon name="sparkle" />
      <span className="visually-hidden">Model for fixes</span>
      <select
        className="model-select"
        value={model ?? status.defaultModel}
        onChange={(e) => {
          claude.setModel(e.target.value);
        }}
      >
        {status.models.map((m) => (
          <option key={m.id} value={m.id}>
            {m.name}
          </option>
        ))}
      </select>
    </label>
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
  else if (view.kind === 'needs-permission') left = 'No sites allowed yet';
  else if (view.kind === 'reading') left = 'Reading';
  else if (view.kind === 'not-jupyter' || view.kind === 'other-site') left = 'Nothing to read';
  return (
    <footer className="statusbar">
      <span className="status-left">{left}</span>
      <ModelMenu claude={claude} />
    </footer>
  );
}

function Note({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="message">
      <h2 className="message-title">{title}</h2>
      {children}
    </section>
  );
}

/** Add a site by its address. Chrome then asks you about that one site; nothing else is granted. */
function SiteForm({
  onAdd,
  label,
}: {
  onAdd: (pattern: string) => Promise<boolean>;
  label: string;
}) {
  const [value, setValue] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  return (
    <form
      className="site-form"
      onSubmit={(e) => {
        e.preventDefault();
        const site = sitePattern(value);
        if (site === null) {
          setProblem(
            'Enter the address Jupyter shows in the address bar, like jupyter.example.edu.',
          );
          return;
        }
        setProblem(null);
        void onAdd(site.pattern).then((granted) => {
          if (!granted) setProblem(`Chrome didn’t allow ${site.host}.`);
        });
      }}
    >
      <label className="site-label" htmlFor="site-input">
        {label}
      </label>
      <div className="site-row">
        <input
          id="site-input"
          className="input"
          type="text"
          inputMode="url"
          autoComplete="url"
          spellCheck={false}
          placeholder="jupyter.example.edu"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
          }}
          aria-invalid={problem !== null}
          aria-describedby={problem !== null ? 'site-problem' : undefined}
        />
        <button type="submit" className="btn" disabled={value.trim() === ''}>
          Allow
        </button>
      </div>
      {problem !== null && (
        <p className="site-problem" id="site-problem" role="alert">
          {problem}
        </p>
      )}
    </form>
  );
}

/**
 * Shown above the list while Claude can't be asked: what's wrong, turned into steps, and
 * Check again. Each problem has its own fix.
 */
function ConnectClaude({ claude }: { claude: Claude }) {
  const { status } = claude;
  if (status.kind === 'checking') return null;
  if (status.kind === 'ready' && status.hasKey) return null;
  let title = 'Connect Claude';
  let body: ReactNode;
  if (status.kind === 'ready') {
    title = 'Add your Claude key';
    body = (
      <p>
        Marginalia&rsquo;s helper is connected but has no Claude API key. Add one in
        Marginalia&rsquo;s Settings on this computer, under AI model, then check again.
      </p>
    );
  } else if (status.problem === 'missing') {
    body = (
      <>
        <p>
          Fixes come from Marginalia on this computer, with the Claude key from its keychain, so no
          key lives in the browser. Run this once in a terminal, in the Python environment
          Marginalia is installed in (in a source checkout, prefix it with <code>.venv/bin/</code>
          ):
        </p>
        <CodeBlock file="Terminal" text={INSTALL_COMMAND} />
      </>
    );
  } else if (status.problem === 'forbidden') {
    const id = browser.runtime.id;
    body =
      id === EXPECTED_ID ? (
        <>
          <p>
            The helper on this computer was set up for another copy of Marginalia. Set it up again:
          </p>
          <CodeBlock file="Terminal" text={INSTALL_COMMAND} />
        </>
      ) : (
        <p>
          The helper only answers Marginalia&rsquo;s own id, and this copy has a different one (
          <code>{id}</code>), usually because it was reloaded from an older build. In{' '}
          <code>chrome://extensions</code>, remove Marginalia, then Load unpacked the{' '}
          <code>extension/.output/chrome-mv3</code> folder again.
        </p>
      );
  } else {
    body = (
      <>
        <p>The helper started, then stopped. This shows what went wrong:</p>
        <CodeBlock file="Terminal" text={CHECK_COMMAND} />
      </>
    );
  }
  return (
    <section className="connect" aria-labelledby="connect-title">
      <h2 className="connect-title" id="connect-title">
        <Icon name="sparkle" />
        {title}
      </h2>
      {body}
      {status.kind === 'unavailable' && <p className="fine">Chrome said: {status.message}</p>}
      <div className="actions">
        <button type="button" className="btn primary" onClick={claude.recheck}>
          Check again
        </button>
      </div>
    </section>
  );
}

function Diff({ proposal }: { proposal: Proposal }) {
  const { kind, source } = proposal.reply.fix;
  const lines =
    kind === 'insert_before' ? diffLines('', source) : diffLines(proposal.expected, source);
  return (
    <figure className="diff">
      <figcaption>
        {kind === 'insert_before'
          ? `New cell before cell ${String(proposal.cellNumber)}`
          : `Change to cell ${String(proposal.cellNumber)}`}
      </figcaption>
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

/** "Claude Sonnet 5.5" for an id the helper listed; the id itself otherwise. */
function modelName(claude: Claude, id: string): string {
  if (claude.status.kind !== 'ready') return id;
  return claude.status.models.find((m) => m.id === id)?.name ?? id;
}

/** Claude's reasoning: three lines, and the rest on request. */
function Reasoning({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.length > 220;
  return (
    <div className="reasoning">
      <p className={long && !open ? 'clamp-3' : undefined}>{text}</p>
      {long && (
        <button
          type="button"
          className="link"
          aria-expanded={open}
          onClick={() => {
            setOpen((o) => !o);
          }}
        >
          {open ? 'Less' : 'More'}
        </button>
      )}
    </div>
  );
}

function FixArea({
  state,
  claude,
  fkey,
  cells,
  onAsk,
}: {
  state: FixState;
  claude: Claude;
  fkey: string;
  cells: number;
  onAsk: () => void;
}) {
  const seconds = useSeconds(state.kind === 'asking' ? state.since : null);
  switch (state.kind) {
    case 'idle':
      return null;
    case 'asking':
      return (
        <div className="suggestion asking" role="status">
          <p className="suggestion-by">
            <Icon name="sparkle" />
            Claude is reading {cells} {cells === 1 ? 'cell' : 'cells'}
            {seconds >= 2 ? ` (${String(seconds)} s)` : '…'}
          </p>
          <span className="skeleton" aria-hidden="true" />
          <span className="skeleton short" aria-hidden="true" />
          <div className="actions">
            <button type="button" className="btn quiet" onClick={() => claude.stop(fkey)}>
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
        <div className="suggestion">
          <p className="suggestion-by">
            <Icon name="sparkle" />
            {modelName(claude, reply.model)} suggests
          </p>
          <p className="suggestion-summary">{reply.summary}</p>
          <Reasoning text={reply.explanation} />
          {reply.fix.kind !== 'none' && <Diff proposal={state.proposal} />}
          <div className="actions">
            {reply.fix.kind === 'none' ? (
              <button type="button" className="btn" onClick={onAsk}>
                Ask again
              </button>
            ) : (
              <button
                type="button"
                className="btn primary"
                aria-busy={busy}
                disabled={busy}
                onClick={() => claude.apply(fkey)}
              >
                {busy && <span className="spinner" aria-hidden="true" />}
                {busy ? 'Applying' : 'Apply'}
              </button>
            )}
            <button
              type="button"
              className="btn quiet"
              disabled={busy}
              onClick={() => claude.dismiss(fkey)}
            >
              Dismiss
            </button>
          </div>
        </div>
      );
    }
    case 'applied':
    case 'undoing':
      return (
        <div className="outcome ok" role="status">
          <Icon name="check" />
          <p>{appliedText(state.proposal)}</p>
          <button
            type="button"
            className="btn quiet"
            disabled={state.kind === 'undoing'}
            onClick={() => claude.undo(fkey)}
          >
            <Icon name="undo" />
            {state.kind === 'undoing' ? 'Undoing' : 'Undo'}
          </button>
        </div>
      );
    case 'failed':
      if (
        state.problem === 'missing' ||
        state.problem === 'forbidden' ||
        state.problem === 'exited'
      )
        return (
          <div className="outcome bad" role="alert">
            <p>Claude isn&rsquo;t connected. The steps are at the top of the panel.</p>
          </div>
        );
      return (
        <div className="outcome bad" role="alert">
          <p>
            {state.message}
            {state.action === 'settings' && ' Open Marginalia’s Settings, under AI model.'}
          </p>
          <div className="outcome-actions">
            {state.action !== 'settings' && (
              <button type="button" className="btn" onClick={onAsk}>
                {state.problem === 'stale' ? 'Ask again' : 'Try again'}
              </button>
            )}
            <button type="button" className="btn quiet" onClick={() => claude.dismiss(fkey)}>
              Dismiss
            </button>
          </div>
        </div>
      );
  }
}

function ErrorNote({
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
  const ready = claude.status.kind === 'ready' && claude.status.hasKey;
  const detailsId = `details-${fkey}`;
  const cell = error.index + 1;
  const fixed = state.kind === 'applied' || state.kind === 'undoing';
  return (
    <li className="note" data-fixed={fixed ? '' : undefined}>
      <button
        type="button"
        className="marker"
        onClick={() => nb.reveal(error.index, error.cellId)}
        aria-label={`Go to cell ${String(cell)}`}
        title={`Go to cell ${String(cell)}`}
      >
        {fixed ? <Icon name="check" /> : cell}
      </button>
      <div className="note-body">
        <p className="ename">{error.ename}</p>
        {error.evalue !== '' && (
          <h3 className="evalue clamp-2" title={error.evalue}>
            {error.evalue}
          </h3>
        )}
        {error.line !== null && (
          <code className="source-line" title={error.where ?? undefined}>
            {error.line}
          </code>
        )}
        <div className="actions">
          {state.kind === 'idle' && (
            <button
              type="button"
              className="btn primary"
              onClick={ask}
              disabled={!ready}
              title={
                ready ? undefined : 'Connect Claude first: the steps are at the top of the panel.'
              }
            >
              <Icon name="sparkle" />
              Fix with Claude
            </button>
          )}
          <button
            type="button"
            className="btn quiet"
            onClick={() => nb.reveal(error.index, error.cellId)}
          >
            <Icon name="goto" />
            Go to cell
          </button>
          <button
            type="button"
            className="btn quiet disclose"
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
        <div className="details" id={detailsId} hidden={!open}>
          {error.where !== null && (
            <p className="fine">
              {error.where}
              {error.raisedIn !== null && `, raised in ${error.raisedIn}`}
            </p>
          )}
          <pre>{error.traceback}</pre>
          <CopyButton
            text={`${error.ename}: ${error.evalue}\n\n${error.traceback}`}
            label="Copy error"
          />
        </div>
        <FixArea
          state={state}
          claude={claude}
          fkey={fkey}
          cells={context.summary.cellCount}
          onAsk={ask}
        />
      </div>
    </li>
  );
}

function Body({ nb, claude }: { nb: Notebook; claude: Claude }) {
  const { view } = nb;
  switch (view.kind) {
    case 'checking':
      return <p className="fine">Looking at this tab…</p>;
    case 'needs-permission':
      return (
        <Note title="Choose where Marginalia may read">
          <p>
            It reads Jupyter notebooks only on sites you allow, and Chrome asks you first. Jupyter
            on this computer, or through an SSH tunnel, is on localhost.
          </p>
          <div className="actions">
            <button type="button" className="btn primary" onClick={nb.allow}>
              Allow localhost
            </button>
          </div>
          <SiteForm onAdd={nb.addSite} label="Jupyter somewhere else? Add its address." />
        </Note>
      );
    case 'other-site':
      return (
        <Note title="Marginalia can’t read this tab">
          <p>
            It reads Jupyter notebooks only on sites you&rsquo;ve allowed. If this tab is a
            notebook, add its address.
          </p>
          <SiteForm onAdd={nb.addSite} label="Notebook address" />
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
          <p className="fine">
            Restarting the kernel isn&rsquo;t enough: the server reads this file when it starts.
          </p>
        </Note>
      );
    case 'reading':
      return <p className="fine">Reading the notebook…</p>;
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
          {view.detail !== null && <p className="fine">{view.detail}</p>}
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
            <p>
              {codeCellCount} code {codeCellCount === 1 ? 'cell' : 'cells'}, all clear. An error
              shows up here as soon as a cell raises one.
            </p>
          </Note>
        );
      return (
        <section>
          <div className="list-head">
            <h2 className="list-title">
              {errors.length} {errors.length === 1 ? 'error' : 'errors'}
            </h2>
            <p className="fine">Nothing changes in the notebook until you press Apply.</p>
          </div>
          {nb.revealProblem !== null && (
            <p className="reveal-problem" role="status">
              {nb.revealProblem}
            </p>
          )}
          <ol className="thread">
            {errors.map((e) => (
              <ErrorNote key={fixKey(e)} error={e} context={context} nb={nb} claude={claude} />
            ))}
          </ol>
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
        {nb.view.kind === 'ready' && <ConnectClaude claude={claude} />}
        <Body nb={nb} claude={claude} />
      </main>
      <StatusBar view={nb.view} claude={claude} />
    </div>
  );
}
