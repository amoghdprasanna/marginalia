# 0032. A live session with Claude: each error its own note, history in every request

**Status:** Accepted, 2026-10-28. Extends [0030](0030-fix-notebook-errors-through-a-desktop-helper.md).

## Context
Debugging a notebook is a chain: fix the missing qutip, rerun, now torch can't load its CUDA
library, fix that, and so on. On the real cluster the panel broke that chain. A fix was keyed
to its *cell*, so when cell 2 raised a new error after the qutip fix, the panel still showed it as
fixed ("Added a cell before cell 2") with no way to ask about the new one. Claude also saw each
error alone, with no idea what had just been tried.

## Decision
- **A fix belongs to an error, not a cell.** Each error's key is its cell id, the run
  (execution count) that raised it and a fingerprint of what it raised. A rerun or a different
  error is a new key: a fresh note with **Fix with Claude**.
- **Each notebook has a session.** Every suggestion and what you did with it (proposed, applied,
  undone, dismissed) is kept per notebook path in `storage.session`, so it lasts as long as the
  browser does and survives closing the panel. The last ten go with every fix request; the
  helper puts them in a `<session>` block before the traceback, and the system prompt tells
  Claude to build on them and not repeat what was undone or dismissed.
- **New errors are asked about by themselves.** An error that appears while the panel is open
  is sent to Claude without a click; errors already there when the panel opens wait for you, so
  opening it never sets off a burst of requests. A switch, *Suggest fixes for new errors*, turns
  this off; it's remembered in the browser. Nothing is ever applied by itself.
- **A suggestion goes stale when its cell changes.** If the cell's source no longer matches what
  Claude saw, the diff and Apply give way to "The cell changed since Claude looked" and *Ask
  again*. The page still refuses a stale edit (0030), but you're told before you press anything.

## Alternatives considered
- **Key by cell, reset on rerun.** Loses the difference between "same error again" and "new
  error", and an applied fix's state would vanish on any rerun.
- **One long chat thread per notebook in the helper.** The helper process ends with the panel;
  a stateless request with a short history is cheaper, survives restarts, and keeps the prompt
  small.
- **Ask about every error on open.** One click to open the panel could cost a dozen model calls.

## Consequences
- Each new error costs one Claude request while auto-suggest is on; the switch is in the list
  heading, next to the count.
- The session lives in the browser, not the notebook: a new browser session starts fresh.
