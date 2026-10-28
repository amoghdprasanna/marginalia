# 0030. Fix notebook errors with Claude, through a helper on your computer

**Status:** Accepted, 2026-10-27. Extends [0029](0029-a-chrome-extension-for-notebooks.md).

## Context
The first stage of the notebook extension listed the cells that raised and stopped there. Asked
to try it on a real notebook, the first thing wanted was the point of the whole feature: *fix*
the error, with Claude. That needs a model call with an API key, and a way to change a cell
that you control.

Marginalia already keeps the Claude key in the system keychain (ADR 0016), knows which model and
effort you chose (ADR 0015), and words API errors for people (`brain.errors`).

## Decision
**The extension asks a small helper on your computer, never the API itself.**
- `marginalia-browser-host` (`marginalia.browser.host`) is a Chrome *native messaging host*:
  Chrome starts it when the panel connects and ends it when the panel closes. It reads your
  settings and the key from the keychain, calls Claude, and answers over stdin/stdout.
- `marginalia-browser-host install` writes the host manifest for Chrome, Chromium, Brave and Edge
  (on Windows, the registry values pointing at it). The manifest allows **one** extension id.
- The extension's id is fixed by a public `key` in its manifest
  (`behgmlfpdfdjcbiogfngmghpbfgaagpa`), wherever it's loaded from, so the manifest can name it.
  The private key isn't needed for an unpacked extension and isn't in the repository.
- The installed app is its own helper: started with a `chrome-extension://` origin as its first
  argument, `app.main` hands over to the helper before any window or Qt exists.

**A fix is one structured call.** The panel sends the cells' sources (no outputs), the failing
cell and its traceback. Nearest cells are kept first within about 60k characters. Claude answers
in a JSON schema: a one-line summary, two to four sentences of explanation, and exactly one of
*replace* (the failing cell's new source), *insert_before* (a new cell, e.g. `%pip install
qutip`) or *none* (the fix is outside the notebook: a file from someone else's computer, a
module to load). It's Claude-only for now; your model is kept if it is a Claude one.

**Nothing changes until you press Apply, and nothing ever runs.**
- The panel shows the change as a line diff. Apply sends one edit to the page, which makes it
  through Jupyter's shared model (`setSource`, `insertCell`, `deleteCell`).
- Each edit carries the source Claude saw. If the cell changed since, the page refuses
  ("The cell changed since Claude looked at it"), never overwriting your work.
- Undo is the reverse edit, checked the same way: replace back, or delete the inserted cell.

## Alternatives considered
- **Call the API from the extension with a key stored in Chrome.** A second copy of the key, in
  extension storage any page bug could reach, and a second place to choose models. Rejected.
- **Talk to the running desktop app over a localhost socket.** Any website could try to connect;
  it needs a token handshake and the app running. Native messaging only answers our extension
  and starts on demand.
- **Let Claude run the cell to check its fix.** Running code on a cluster without you pressing
  anything is the line not to cross. You run it.
- **A free-form answer with a code block.** Parsing prose for code breaks; the schema makes the
  three kinds of fix explicit and testable.

## Consequences
- One setup step per computer (`marginalia-browser-host install`); the panel shows it, with
  Copy, when Chrome can't find the helper.
- On macOS, the first fix may ask to let the helper read the Marginalia keychain item if the
  key was saved by the installed app rather than this Python. *Always Allow* once.
- Tests: the helper's framing, request parsing, context budget, reply parsing and errors run
  against a fake client (`tests/unit/browser`). The e2e suite registers a fake helper in the
  test browser's profile and drives ask → diff → Apply → Undo, and the stale refusal, against a
  real Notebook 7 server.
- The panel's mascot also changed with this stage: Ket is now an original round lamb, with the
  qubit kept as its Bloch-sphere bell (docs/design.md).
