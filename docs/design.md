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
- Errors get the only red in the palette; amber stays the colour of answers and markers.

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
- Muted text (#9BA3BC on #1B2031) has 6.4:1 contrast; body text is 14 px; nothing is
  smaller than 12 px.
- Status never relies on colour alone: the setup check marks each row with a tick, "!", a dash or
  "?" as well as green, amber or grey, and names it for screen readers.
- Disabled looks disabled: fainter text (`DISABLED_HEX`) and a flatter button, never the amber of
  a primary button; a disabled Save is not a dim orange one.
- The orb lights its rim under the pointer, so it reads as something to click.
- Windows never grow taller than the screen; Settings scrolls with its buttons pinned below.

**8. One visual language.** (Consistency)
- Slate glass for text surfaces, amber for the answer's marks and primary actions, red for errors.
- One label column per window, so fields line up; one stylesheet (`theme.DIALOG_STYLE`) for every
  ordinary window.
- One highlighted (amber) button per window, and it is the next step: in the setup check, the
  first required fix until everything required is ready, then *Start using Marginalia*.
- A checkbox's help line starts under its words, not under the box, measured from the style.
- Every button has three states you can tell apart: hover lightens, pressing darkens, keyboard
  focus draws a ring. The ring never changes the button's size.
- A problem in Settings is shown on the page of the field it's about, and goes away once you
  change something.
- Windows with wrapped text are sized to it (`theme.fit_height`): no clipped lines, no empty bands.

**9. Empty states teach.** (Help and documentation)
- An empty journal is one centred message under the qubit mark: what will appear here and how to
  make it appear. A search with no results says so, and what to try.

## Tokens (`ui/theme.py`)

Every colour is a token in `theme.py`; no other UI module writes a colour literal (a test checks).
`tests/ui/test_theme.py` checks each text colour against each surface it's drawn on (4.5:1, WCAG
1.4.3), field edges at 3:1 (1.4.11), and that *ready*, *needs you*, *went wrong* and *muted* stay
at least 20 apart (CIE76 ΔE) under simulated protanopia, deuteranopia and tritanopia.

| Token | Value | Use | On slate |
|---|---|---|---|
| `SLATE_HEX` | `#1B2031` | windows and panels (96% opaque when floating) | |
| `SIDEBAR_HEX` | `#161A28` | the Settings sidebar, a shade under | |
| `RAISED_HEX` | `#262C42` | tooltips and pop-up lists, a shade over | |
| `TEXT_HEX` | `#ECEFF7` | body text | 14.1:1 |
| `TEXT_SOFT_HEX` | `#C4CADB` | the keys in a hint row | 9.9:1 |
| `MUTED_HEX` | `#9BA3BC` | secondary text, hints | 6.4:1 |
| `DISABLED_HEX` | `#6B7290` | controls you can't use now | 3.4:1 (exempt) |
| `FIELD_EDGE_HEX` | `#6B7391` | edge of text fields and checkboxes | 3.5:1 |
| `AMBER_HEX` | `#FFB224` | markers, the qubit, primary buttons, focus | 9.0:1 |
| `AMBER_HOVER_HEX`, `AMBER_DOWN_HEX` | `#FFC452`, `#E99A0B` | the primary button hovered, pressed | |
| `OK_HEX` | `#6EE7B7` | the setup check's "ready" (a mint, clear of amber) | 10.6:1 |
| `ERROR_HEX` | `#F2735F` | error mark and error text only | 5.7:1 |

Surfaces inside a window are white laid over the slate, by `FILL_*` alpha: card 6, hover 10,
field 12, button 16, selected 26, hovered button 28; `LINE` (24) for dividers and card edges.

**Why these two changed.** The old "ready" green (`#6ECC8C`) and error coral (`#FF8A80`) were
9.6 apart to deuteranopes, about 1 in 16 men: nearly the same colour. The mint and warm red were
picked by searching hues for the widest worst-case gap across the three kinds of colour blindness
while keeping 4.5:1 on every surface; the worst pair is now 28 apart. Field edges went from 1.4:1
(an outline you could barely see) to 3.5:1.

## Checking a change

`python` + `QT_QPA_PLATFORM=offscreen` can render any widget to PNG (`widget.grab().save(...)`);
look at every state you touched, at the smallest screen you support. Then ask of each state:
what is it doing, how do I get out, and what do I do next?
