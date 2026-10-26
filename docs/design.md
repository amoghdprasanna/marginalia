# Interface design

Marginalia floats over whatever you are reading. Every design choice follows from that: it must
help without taking over the screen, and you must never have to wonder what it is doing.
These are the rules the UI follows, with where each shows up. Check a UI change against them.

## Principles

**1. Always say what is happening.** (Visibility of system status)
- The bubble has one state at a time, each with words: *Reading your screen…*, *Thinking… 7 s*
  (seconds appear after 3, so a slow answer never looks frozen), *Writing…*, *Answered in 4.2 s*,
  or an error.
- The orb spins while an answer is on its way, and stops when nobody is waiting for one.
- The listen box shows a live level meter and a timer; *Transcribing…* after you stop.

**2. Every state has a visible way out.** (User control)
- Working or writing: a **Stop** button, not just the small ✕ or a key you have to know.
- Esc closes whatever has focus (bubble, ask box, listen box, Settings, Journal).
- Cancelling a question ends its thread, so what you see is what the next question remembers.

**3. Errors say what happened and offer the fix as a button.** (Help users recover)
- `BrainError.action` says how to recover: **Try again** (rate limit, network, server trouble),
  **Open Settings** (key or model problems), **Open setup check** (screen can't be captured).
  The likeliest fix is the first, highlighted button.
- Messages are plain language and name the place to fix things ("in Settings"), never an
  environment variable.
- An error with nothing to press (Claude declined) keeps the follow-up field: ask it another way.
- Errors get the only coral in the palette; amber stays the colour of answers and markers.

**4. Speak the reader's language; details on demand.** (Match the real world, minimalism)
- "Claude Sonnet 5.5 · Faster, about half the price", not `claude-sonnet-5-5`; "Thinking:
  Thorough", not `effort: high`.
- The bubble footer says *Answered in 4.2 s*; model, timings and OCR counts are in its tooltip.
- Settings you rarely need (max tokens, high-res images, console detail, eval cases) are on the
  last page, *Advanced*.
- The journal names the model in words ("Claude Opus 5.5"), as the bubble does.
- Help text sits under a setting only when its label isn't enough.

**5. Show, don't make people remember.** (Recognition over recall)
- The chooser that opens on every orb click shows your shortcuts, so they're learned by use.
- Journal and Settings are one click from the orb (and `J`, `,`), not hidden behind right-click.
- If Speak is greyed out, the chooser says why, in text, not only in a tooltip, and its tip stops
  teaching the voice key.
- Settings is a sidebar of topics (AI model, Shortcuts, Voice and reading, General, Advanced), one
  page each: every topic is in view, no page needs scrolling, and the window doesn't change size
  as you switch. It opens on *AI model*, where every "Open Settings" fix leads.
- The setup window ends with *How to ask*, using your actual keys.
- *Show 2 places again* brings the markers back after they settle.

**6. Don't offer what does nothing.** (Error prevention)
- Save is enabled only when something changed. Send is enabled only when there is text.
- Fields set by an environment variable or a command-line switch are locked and say by what.
- A field that does nothing while its switch is off is greyed out: the shortcut boxes without
  *Shortcuts work in any app*, the speech model and hold-to-talk key without *Ask by voice*.
- Nothing to remove, no Remove button; nothing in the journal, no box to ask in and no Copy.
- Shortcuts are recorded by pressing them, and must include a modifier.

**7. Easy to hit, easy to see.** (Fitts, accessibility)
- Clickable things are at least 26 px; the close button got bigger for that reason.
- Keyboard focus is always visible (amber ring; a light ring on amber buttons).
- Muted text (#9BA3BC on #1B2031) has about 6.6:1 contrast; body text is 14 px; nothing is
  smaller than 12 px.
- Status never relies on colour alone: the setup check marks each row with a tick, "!", a dash or
  "?" as well as green, amber or grey, and names it for screen readers.
- Disabled looks disabled: fainter text (`DISABLED_HEX`) and a flatter button, never the amber of
  a primary button; a disabled Save is not a dim orange one.
- The orb lights its rim under the pointer, so it reads as something to click.
- Windows never grow taller than the screen; Settings scrolls with its buttons pinned below.

**8. One visual language.** (Consistency)
- Slate glass for text surfaces, amber for the answer's marks and primary actions, coral for errors.
- One label column per window, so fields line up; one stylesheet (`theme.DIALOG_STYLE`) for every
  ordinary window.
- One highlighted (amber) button per window, and it is the next step: in the setup check, the
  first required fix until everything required is ready, then *Start using Marginalia*.
- A checkbox's help line starts under its words, not under the box (`theme.CHECK_INDENT`).

**9. Empty states teach.** (Help and documentation)
- An empty journal is one centred message under the qubit mark: what will appear here and how to
  make it appear. A search with no results says so, and what to try.

## Tokens (`ui/theme.py`)

| Token | Value | Use |
|---|---|---|
| `SLATE` | `#1B2031` at 96% | panel and window background |
| `TEXT_HEX` | `#ECEFF7` | body text |
| `MUTED_HEX` | `#9BA3BC` | secondary text, hints |
| `AMBER_HEX` | `#FFB224` | markers, the qubit mark, primary buttons, focus |
| `ERROR_HEX` | `#FF8A80` | error mark and error text only |
| `OK_HEX` | `#6ECC8C` | the setup check's "ready" |
| `DISABLED_HEX` | `#6B7290` | text of controls you can't use right now |
| `SIDEBAR_HEX` | `#161A28` | the Settings sidebar, a shade under the slate |

## Checking a change

`python` + `QT_QPA_PLATFORM=offscreen` can render any widget to PNG (`widget.grab().save(...)`);
look at every state you touched, at the smallest screen you support. Then ask of each state:
what is it doing, how do I get out, and what do I do next?
