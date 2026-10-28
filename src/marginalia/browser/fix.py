"""Fix a failing notebook cell with Claude: what went wrong, and one change you can apply (ADR 0030).

The extension sends the notebook's cells (sources only, no outputs), the failing cell and its
traceback. Claude answers in a fixed JSON shape: a one-line summary, a short explanation, and a
fix that either replaces the failing cell, inserts a cell before it (`%pip install qutip`), or is
"none" when the change belongs outside the notebook. Nothing here runs code.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..brain.errors import friendly, missing_key
from ..brain.types import BrainError

FIX_KINDS = ("replace", "insert_before", "none")

FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "What went wrong, in one plain sentence."},
        "explanation": {
            "type": "string",
            "description": "Two to four short sentences: why it failed and what the change does.",
        },
        "fix": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(FIX_KINDS)},
                "source": {
                    "type": "string",
                    "description": "replace: the failing cell's full new source. insert_before: the new "
                    "cell's source. none: empty.",
                },
            },
            "required": ["kind", "source"],
            "additionalProperties": False,
        },
    },
    "required": ["summary", "explanation", "fix"],
    "additionalProperties": False,
}

SYSTEM = """You fix errors in Jupyter notebooks for a physics researcher. You get the notebook's \
cells (outputs left out), the cell that raised, and its traceback.

Answer with:
- summary: what went wrong, one plain sentence.
- explanation: two to four short sentences on why, and what your change does. No markdown.
- fix, exactly one of:
  - replace: the failing cell's complete new source. Change as little as possible; keep every \
other line, comment and blank line as it was.
  - insert_before: a new cell to run before the failing one, when the fix is a setup step. For a \
missing module, `%pip install <package>` (the pip name, e.g. `%pip install qutip`).
  - none, with an empty source: when the fix is outside the notebook (a file that only exists on \
another computer, a cluster module to load) or you can't tell. Say what to do in the explanation.

Never invent data, results or files. A path from someone else's computer (C:\\Users\\..., \
/Users/...) won't exist here: point to a path relative to the notebook only if the notebook \
itself shows where the file lives; otherwise choose none and say which file is needed."""

# Characters of notebook context: the failing cell and traceback always fit; other cells are
# added nearest-first until this runs out (about 15k tokens).
CONTEXT_BUDGET = 60_000
TRACEBACK_TAIL = 8_000


@dataclass(frozen=True)
class Cell:
    index: int
    kind: str
    source: str


@dataclass(frozen=True)
class FixRequest:
    path: str
    kernel: str | None
    cells: tuple[Cell, ...]
    failing: int  # index into the notebook, from 0
    ename: str
    evalue: str
    traceback: str


@dataclass(frozen=True)
class Fix:
    summary: str
    explanation: str
    kind: str
    source: str
    model: str

    def as_message(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "explanation": self.explanation,
            "fix": {"kind": self.kind, "source": self.source},
            "model": self.model,
        }


def _str(obj: dict, key: str, default: str | None = None) -> str:
    value = obj.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text")
    return value


def parse_request(obj: Any) -> FixRequest:
    """The extension's request, checked; ValueError says what's wrong with it."""
    if not isinstance(obj, dict):
        raise ValueError("the request must be an object")
    raw_cells = obj.get("cells")
    if not isinstance(raw_cells, list) or not raw_cells:
        raise ValueError("cells must be a non-empty list")
    cells = []
    for i, c in enumerate(raw_cells):
        if not isinstance(c, dict):
            raise ValueError(f"cell {i} must be an object")
        cells.append(Cell(i, _str(c, "kind", "code"), _str(c, "source", "")))
    failing = obj.get("failing")
    if not isinstance(failing, int) or isinstance(failing, bool) or not 0 <= failing < len(cells):
        raise ValueError("failing must be the index of one of the cells")
    kernel = obj.get("kernel")
    return FixRequest(
        path=_str(obj, "path", "notebook.ipynb"),
        kernel=kernel if isinstance(kernel, str) else None,
        cells=tuple(cells),
        failing=failing,
        ename=_str(obj, "ename"),
        evalue=_str(obj, "evalue", ""),
        traceback=_str(obj, "traceback", ""),
    )


def _cell_text(cell: Cell, failing: bool) -> str:
    mark = ' failing="true"' if failing else ""
    return f'<cell number="{cell.index + 1}" type="{cell.kind}"{mark}>\n{cell.source}\n</cell>'


def build_user_text(req: FixRequest, budget: int = CONTEXT_BUDGET) -> str:
    """The notebook as Claude sees it: cells in order, nearest to the failing one kept first."""
    failing = req.cells[req.failing]
    chosen = {req.failing: _cell_text(failing, True)}
    used = len(chosen[req.failing])
    # Nearest first, earlier cells before later ones at the same distance: imports and
    # definitions usually come before the cell that uses them.
    order = sorted(
        (c for c in req.cells if c.index != req.failing),
        key=lambda c: (abs(c.index - req.failing), c.index > req.failing),
    )
    for cell in order:
        text = _cell_text(cell, False)
        if used + len(text) > budget:
            continue
        chosen[cell.index] = text
        used += len(text)
    left_out = len(req.cells) - len(chosen)
    traceback = req.traceback[-TRACEBACK_TAIL:]
    head = f"Notebook: {req.path}" + (f" (kernel: {req.kernel})" if req.kernel else "")
    parts = [
        head,
        f"Cell {req.failing + 1} of {len(req.cells)} raised {req.ename}: {req.evalue}",
        *(chosen[i] for i in sorted(chosen)),
    ]
    if left_out:
        parts.append(f"({left_out} cells left out for length.)")
    parts.append(f"<traceback>\n{traceback}\n</traceback>")
    return "\n\n".join(parts)


def parse_fix(raw: str, model: str) -> Fix:
    """Claude's JSON reply as a Fix; anything off becomes a BrainError the panel can show."""
    try:
        data = json.loads(raw)
        fix = data["fix"]
        kind, source = fix["kind"], fix["source"]
        summary, explanation = data["summary"], data["explanation"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise BrainError("Claude's answer came back in an unexpected shape. Try again.", "retry") from exc
    if kind not in FIX_KINDS or not all(isinstance(v, str) for v in (source, summary, explanation)):
        raise BrainError("Claude's answer came back in an unexpected shape. Try again.", "retry")
    if kind != "none" and not source.strip():
        kind, source = "none", ""
    return Fix(summary.strip(), explanation.strip(), kind, source if kind != "none" else "", model)


class NotebookFixer:
    """One Messages API call per fix. `client` is injectable so tests never touch the network."""

    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self, cfg, api_key: str | None, client=None) -> None:
        self.cfg = cfg
        self.model = cfg.model
        self.client = client
        if self.client is None and api_key:
            import anthropic

            self.client = anthropic.Anthropic(api_key=api_key)

    def build_request(self, req: FixRequest) -> dict:
        return {
            "model": self.model,
            "max_tokens": self.cfg.max_tokens,
            "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": [{"type": "text", "text": build_user_text(req)}]}],
            "output_config": {"effort": self.cfg.effort, "format": {"type": "json_schema", "schema": FIX_SCHEMA}},
            "betas": [self.FALLBACK_BETA],
            "fallbacks": "default",
        }

    def fix(self, req: FixRequest) -> Fix:
        import anthropic

        if self.client is None:
            raise missing_key("Claude")
        try:
            with self.client.beta.messages.stream(**self.build_request(req)) as stream:
                for _ in stream.text_stream:
                    pass
                resp = stream.get_final_message()
        except anthropic.APIError as exc:
            raise friendly(anthropic, exc, "Claude", self.model) from exc
        if resp.stop_reason == "refusal":
            raise BrainError("Claude declined to fix this one.")
        if resp.stop_reason == "max_tokens":
            raise BrainError("Claude's answer was cut off. Raise Max tokens in Settings, then try again.", "settings")
        raw = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        return parse_fix(raw, getattr(resp, "model", self.model))
