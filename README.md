# Marginalia (prototype)

A study companion that floats over your screen. Press a shortcut (or click the orb), ask about
whatever you're reading or watching, and it answers in a small bubble while amber markers fly to
the parts of the screen it's talking about.

![Asking](docs/ask.png)
![Answer with pointers](docs/answer.png)

## Run it

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-ocr.txt  # optional, improves pointing
pip install -r requirements-voice.txt # optional, ask by voice (local Whisper)
cp .env.example .env                 # then paste your Anthropic API key into .env

python run.py --demo                 # try the interface with canned answers, no key needed
python run.py                        # the real thing
```

## Use it

- **Ctrl+Alt+Space** asks about exactly where your mouse is. Type the question, press Enter.
- **The orb** (right edge of the screen) asks about wherever your mouse last rested. Click it and
  pick **Type** or **Speak**. Speaking ends on a short pause (or Enter/click); Esc cancels.
  Drag the orb anywhere; right-click it to quit.
- **Follow-ups** in the bubble re-capture the screen first, so they work while a lecture plays.
- **Esc or the close button** ends the thread and clears the markers.
- Every question, answer and screenshot is saved to `~/Marginalia/doubts/<date>.md`.

## Platform notes

| | |
|---|---|
| **macOS** | Grant *Screen Recording*, *Accessibility* and (for voice) *Microphone* to your terminal (or Python) in System Settings > Privacy & Security, then restart the terminal. A blank screenshot means Screen Recording is missing. If the hotkey crashes or does nothing, run with `--no-hotkey` and use the orb. |
| **Windows** | Works as is. If your antivirus flags the keyboard hook, use `--no-hotkey`. |
| **Linux** | Use an **X11** session for now. Wayland blocks global hotkeys, screen grabs and free window placement; it needs portal-based capture, planned for later. |

## How it works

```
shortcut / orb
   -> hide own windows, grab the screen under the cursor (Qt)
   -> OCR starts in the background while you type
   -> two images: full screen + close-up around the cursor (red ring marks the cursor)
      resized exactly the way the API resizes, so returned coordinates line up 1:1
   -> model replies with JSON: answer + up to 4 points (pixel coords, optional OCR line id)
   -> points snap onto OCR lines when the two agree, then map back to screen coordinates
   -> overlay animates markers; bubble picks a spot that covers neither cursor nor targets
```

| File | Job |
|---|---|
| `marginalia/capture.py` | Screen grab, HiDPI mapping, image resizing, cursor ring |
| `marginalia/ocr.py` | Optional RapidOCR text lines with boxes |
| `marginalia/brain.py` | Prompt, API call, lenient JSON parsing, demo mode |
| `marginalia/pointing.py` | Point resolution and snapping, bubble placement |
| `marginalia/ui.py` | Orb, type/speak chooser, ask and listen boxes, answer bubble, pointer overlay |
| `marginalia/voice.py` | Optional mic recording and local Whisper transcription |
| `marginalia/app.py` | Wiring, threads, hotkey, follow-ups, journal |
| `eval/run_eval.py` | Accuracy harness: pointing hit rate and answer checks |

## Measure accuracy

```bash
python eval/run_eval.py            # runs every case in eval/cases
python eval/run_eval.py --no-ocr   # compare with OCR off
```

Whenever an answer or pointer is wrong in real use, copy its screenshot from
`~/Marginalia/doubts/shots/` into a new folder under `eval/cases/` and write a `case.json`
(see the docstring in `eval/run_eval.py`). Aim for 30+ real cases before changing prompts or models.
