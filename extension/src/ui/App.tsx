import { useState, type ReactNode } from 'react';
import { SERVER_CONFIG_LINES } from '@/src/core/access';
import type { CellError } from '@/src/core/notebook';
import { useNotebook } from './connection';
import { Ket, type Mood } from './Ket';
import { splitPath, type View } from './view';

const CONFIG_TEXT = SERVER_CONFIG_LINES.join('\n');
const CONFIG_FILE = '~/.jupyter/jupyter_server_config.py';

function moodOf(view: View): Mood {
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

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="button small"
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1600);
        });
      }}
    >
      {copied ? 'Copied' : label}
    </button>
  );
}

function Head({ view }: { view: View }) {
  let title: ReactNode = 'Marginalia';
  let sub: ReactNode = null;
  if (view.kind === 'ready') {
    const { name, folder } = splitPath(view.path);
    title = name;
    sub = (
      <>
        {folder !== null && <span className="subtitle">{folder}</span>}
        {view.kernel.name !== null && (
          <span className="kernel">
            <span className="kernel-dot" data-status={view.kernel.status ?? 'unknown'} />
            {view.kernel.status !== null
              ? `${view.kernel.name}, ${view.kernel.status}`
              : view.kernel.name}
          </span>
        )}
      </>
    );
  }
  return (
    <header className="head">
      <Ket mood={moodOf(view)} />
      <div className="head-text">
        <h1 className="title">{title}</h1>
        {sub}
      </div>
    </header>
  );
}

function Note({ children }: { children: ReactNode }) {
  return <section className="note">{children}</section>;
}

function ErrorCard({
  error,
  cellCount,
  onReveal,
}: {
  error: CellError;
  cellCount: number;
  onReveal: () => void;
}) {
  const copyText = `${error.ename}: ${error.evalue}\n\n${error.traceback}`;
  return (
    <li className="error-card">
      <div className="cell-label">
        <span className="prompt">[{error.executionCount ?? ' '}]</span>
        <span>
          Cell {error.index + 1} of {cellCount}
        </span>
      </div>
      <p className="exception">
        <span className="ename">{error.ename}</span>
        {error.evalue !== '' && <>: {error.evalue}</>}
      </p>
      {error.where !== null && (
        <div className="where">
          {error.where}
          {error.line !== null && <code className="line">{error.line}</code>}
        </div>
      )}
      <details className="traceback">
        <summary>Full traceback</summary>
        <pre>{error.traceback}</pre>
      </details>
      <div className="actions">
        <button type="button" className="button small" onClick={onReveal}>
          Go to cell
        </button>
        <CopyButton text={copyText} label="Copy error" />
      </div>
    </li>
  );
}

function Body({ nb }: { nb: ReturnType<typeof useNotebook> }) {
  const { view } = nb;
  switch (view.kind) {
    case 'checking':
      return <p className="summary-sub">Looking at this tab…</p>;
    case 'needs-permission':
      return (
        <Note>
          <h2 className="summary">Read your notebooks</h2>
          <p>
            Marginalia reads Jupyter notebooks on UMD&rsquo;s servers and on your own computer, and
            no other sites. Chrome asks once.
          </p>
          <div className="actions">
            <button type="button" className="button primary" onClick={nb.allow}>
              Allow access
            </button>
          </div>
        </Note>
      );
    case 'other-site':
      return (
        <Note>
          <h2 className="summary">Nothing to read here</h2>
          <p>
            Marginalia reads notebooks on UMD&rsquo;s Jupyter and on localhost. Switch to a notebook
            tab and Ket wakes up.
          </p>
        </Note>
      );
    case 'unreachable':
      return (
        <Note>
          <h2 className="summary">Reload to connect</h2>
          <p>This tab was open before Marginalia could read it. Reloading it connects them.</p>
          <div className="actions">
            <button type="button" className="button primary" onClick={nb.reload}>
              Reload tab
            </button>
          </div>
        </Note>
      );
    case 'not-jupyter':
      return (
        <Note>
          <h2 className="summary">This page isn&rsquo;t Jupyter</h2>
          <p>Open a notebook in this tab and Ket wakes up.</p>
        </Note>
      );
    case 'needs-setting':
      return (
        <Note>
          <h2 className="summary">One setting on the server</h2>
          <p>
            {view.appName} lets an extension read a notebook only when its server allows it. Add
            these lines to this file on the cluster, then start a new Jupyter session.
          </p>
          <figure className="config">
            <figcaption className="config-head">
              <code>{CONFIG_FILE}</code>
              <CopyButton text={CONFIG_TEXT} label="Copy" />
            </figcaption>
            <pre>{CONFIG_TEXT}</pre>
          </figure>
          <p className="fine">
            Restarting the kernel isn&rsquo;t enough: the server reads this file when it starts. On
            Open OnDemand, delete the session and launch a new one.
          </p>
        </Note>
      );
    case 'reading':
      return <p className="summary-sub">Reading the notebook…</p>;
    case 'problem':
      if (view.problem === 'no-notebook')
        return (
          <Note>
            <h2 className="summary">Open a notebook</h2>
            <p>Marginalia reads the notebook open in this tab. Open one from the file list.</p>
          </Note>
        );
      return (
        <Note>
          <h2 className="summary">
            {view.problem === 'no-app'
              ? 'Jupyter didn’t share the notebook'
              : 'This Jupyter looks different'}
          </h2>
          <p>
            {view.problem === 'no-app'
              ? 'The server setting is on, but the page never made the notebook available. Reload the tab; if it happens again, the server may be older than Notebook 7.'
              : 'Its notebook didn’t have the shape Marginalia expects, so reading stopped. Reloading may help.'}
          </p>
          {view.detail !== null && <p className="fine">{view.detail}</p>}
          <div className="actions">
            <button type="button" className="button primary" onClick={nb.reload}>
              Reload tab
            </button>
          </div>
        </Note>
      );
    case 'ready': {
      const { errors, cellCount, codeCellCount } = view.summary;
      if (errors.length === 0)
        return (
          <div>
            <h2 className="summary">No cell has an error</h2>
            <p className="summary-sub">
              {codeCellCount} code {codeCellCount === 1 ? 'cell' : 'cells'}. An error shows up here
              as soon as a cell raises one.
            </p>
          </div>
        );
      return (
        <>
          <div>
            <h2 className="summary">
              {errors.length} {errors.length === 1 ? 'cell raised an error' : 'cells raised errors'}
            </h2>
            {nb.revealProblem !== null && (
              <p className="reveal-problem" role="status">
                {nb.revealProblem}
              </p>
            )}
          </div>
          <ul className="errors">
            {errors.map((e) => (
              <ErrorCard
                key={e.cellId ?? e.index}
                error={e}
                cellCount={cellCount}
                onReveal={() => nb.reveal(e.index, e.cellId)}
              />
            ))}
          </ul>
        </>
      );
    }
  }
}

export function App() {
  const nb = useNotebook();
  return (
    <main className="panel">
      <Head view={nb.view} />
      <Body nb={nb} />
    </main>
  );
}
