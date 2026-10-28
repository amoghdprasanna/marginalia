# 0029. A Chrome extension for notebooks, through Jupyter's own app object

**Status:** Accepted, 2026-10-27. The first stage only reads; edits, explanations and tests come
in later stages with their own records (the bridge to the desktop app is 0030).

## Context
A common way to hit errors is a Jupyter notebook running on a cluster (UMD's, through Open
OnDemand) and open in Chrome. A screenshot sees only the cells on screen, OCR mangles
tracebacks, and nothing in the desktop app can change a cell. To help with a notebook, Marginalia
has to read the real cells and outputs, and later write to them, from inside the browser.

The cluster serves **Jupyter Notebook 7**, which is JupyterLab 4's application in a
one-notebook layout. Verified in `jupyter/notebook` (7.0.0 through 7.6.3, 2026-09-21):

- `notebook/app.py` has `JupyterNotebookApp.expose_app_in_browser` (default `False`), passed to
  the page as `exposeAppInBrowser` in the `#jupyter-config-data` JSON.
- `app/index.template.js` sets `window.jupyterapp = app` when it is `true`. Through `app` a script
  reaches the open `NotebookPanel`: its path, kernel, and `content.model.cells`, each of which
  serialises to an nbformat cell with `toJSON()`.

The editor is CodeMirror 6, as in Lemma (the Overleaf extension), so Lemma's decisions about the
MAIN world, a validated message protocol and stale-edit rejection carry over.

Claude in Chrome, the obvious alternative, drives a tab with screenshots and clicks, loses its
connection, and acts on a tab that changed under it. Those failures shaped the rules below.

## Decision
**A Manifest V3 extension in `extension/`**, in this repository, built like Lemma: WXT, React,
strict TypeScript, Vitest, Playwright, exact versions. Same repository, so the extension and the
desktop app can change their shared protocol in one commit.

**Reach the notebook through `window.jupyterapp`, not the DOM.**
- A MAIN-world content script reads the open notebook from `app.shell.currentWidget` and sends a
  snapshot built from `cell.toJSON()`: nbformat is a published, versioned format, so the parsing
  lives in a pure, tested core (`src/core/`) and does not depend on Jupyter's widget classes.
- The isolated content script reads `#jupyter-config-data` itself. It says exactly why access is
  missing: not a Jupyter page, `exposeAppInBrowser` off (the panel shows the one config line to
  add), or the app object never appeared.
- Every call into the page is duck-typed and wrapped: Jupyter is untrusted code that can change,
  and a failure becomes a reason code with a sentence, never silence.

**Permissions are asked once, for named sites.** `optional_host_permissions` lists
`https://*.umd.edu/*` and local Jupyter (`localhost`, `127.0.0.1`). The panel's *Allow* button
asks for them; only then are the content scripts registered (`scripting.registerContentScripts`).
No `tabs` permission and no access to any other site.

**The background keeps no state.** Chrome stops an idle MV3 service worker after about 30 s, and
an extension that remembers tabs in a worker variable forgets them. Ours only registers scripts
when permissions change; Chrome persists the registrations.

**Every message is tied to its tab and validated.** Contexts talk in a versioned, zod-checked
schema (`{ ns: 'marginalia', v, type, payload }`); anything else is dropped. The panel follows the
active tab and opens a port to that tab's content script, so an answer never lands on the wrong
tab. Every allowed page answers, Jupyter or not, so a silent tab means "reload to connect", not a
guess. A reload drops the port and the panel reconnects. The page only reads while a panel is
connected, so a closed panel costs nothing. The MAIN world shares the page's realm, so it only
answers what it's asked.

**Marginalia never clicks around your tab.** It reads the model and, in later stages, writes
through it; it never moves your mouse or waits on the page's dialogs. Browser automation
(Playwright, for tests) runs in its own window and profile.

**Tests run against a real Notebook 7**, not a mock: Playwright's global setup starts
`notebook==7.6.3` with `uvx`, on a fixture notebook whose saved outputs hold a traceback, and loads
the built extension. A test build (`MARGINALIA_E2E=1`) grants `127.0.0.1` up front, because a
test can't click Chrome's permission prompt.

**Ket, the panel's qubit.** The desktop orb's qubit (ring, equator, state dot) becomes a
character. Its shapes come from one pure module (`src/mascot/ket.ts`) that draws the panel's SVG
and the packaged icons, as Oswald does in Lemma.

## Alternatives considered
- **Read the DOM.** Partial (Jupyter renders lazily and CodeMirror only the viewport), and the
  later edit stage would bypass the notebook model and its undo.
- **Jupyter's REST API.** Reads the *saved* file, not what's in the tab, and writing it races the
  open editor ("file changed on disk").
- **A JupyterLab extension installed on the cluster.** The cleanest handle, but it needs `pip
  install` into whichever environment runs the server, and a build per JupyterLab release. One
  config line is less to ask. If a future cluster forbids that line, this is the fallback.
- **`.cm-content`'s `cmView` back-reference.** Undocumented CodeMirror internals.
- **Claude in Chrome or Playwright MCP on your own tab.** Screenshot-and-click is slow and
  brittle, and since Chrome 136 remote debugging can't attach to your everyday profile anyway.
- **A separate repository.** The protocol to the desktop app would drift between two histories.

## Consequences
- You add one line to `~/.jupyter/jupyter_notebook_config.py` on the cluster and start a new
  session. It also lets any script on that page use the app, but any script on that page could
  already run code in your kernel through the server, so little is added.
- `window.jupyterapp` is a documented switch but not a stable API; the duck-typed adapter and the
  e2e suite on a pinned Notebook version are the guard, and upgrading the pin is deliberate.
- CI gains a Node job (typecheck, lint, unit tests, build) and an e2e job that needs `uv`.
