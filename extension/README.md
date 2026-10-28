# Marginalia for Jupyter (Chrome extension)

A side panel that reads the Jupyter notebook in the current tab and lists the cells that raised an
error: the exception, where it was raised, the line, and the full traceback, with **Go to cell**.
It updates as cells run. Ket, the qubit, shows what it's doing. Why it works this way:
[ADR 0029](../docs/adr/0029-a-chrome-extension-for-notebooks.md).

It reads notebooks on `*.umd.edu` and on your own computer (`localhost`, `127.0.0.1`), asks Chrome
for that once, and makes no network requests.

## Install (from this repository)

```bash
cd extension
npm install
npm run build          # writes .output/chrome-mv3
```

Then in Chrome: `chrome://extensions` → turn on **Developer mode** → **Load unpacked** → choose
`extension/.output/chrome-mv3`. Pin Marginalia from the puzzle-piece menu and click it to open the
panel. After `git pull`, run `npm run build` again and press the reload arrow on the extension's
card.

## Let it read the notebook

Jupyter shares its notebook with extensions only when the server allows it. On the cluster, add
these lines to `~/.jupyter/jupyter_server_config.py`, then start a new Jupyter session (on Open
OnDemand: delete the session and launch a new one; a kernel restart isn't enough):

```python
c.JupyterNotebookApp.expose_app_in_browser = True
c.LabApp.expose_app_in_browser = True
```

The panel says when this is missing and has the lines ready to copy.

## Develop

| Command            | What it does                                                                                                            |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `npm run dev`      | WXT dev build with reload                                                                                               |
| `npm run check`    | types, lint, formatting, unit tests                                                                                     |
| `npm run test:e2e` | builds the e2e variant and runs Playwright against two real Notebook servers (needs [`uv`](https://docs.astral.sh/uv/)) |
| `npm run icons`    | redraws `public/icon/*.png` from Ket's shapes (`src/mascot/ket.ts`)                                                     |

Layout: `src/core` (pure: nbformat, page config), `src/mascot` (Ket's shapes), `src/messaging`
(the validated protocol), `src/adapters/jupyter` (the page script and its bridge), `src/ui` (the
panel), `entrypoints` (WXT entry points).
