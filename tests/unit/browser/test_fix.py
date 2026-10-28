"""Fixing a notebook cell with a fake Claude: the request, the context, the reply, the errors."""
import json

import anthropic
import httpx2
import pytest
from helpers import fake_client

from marginalia.brain.types import BrainError
from marginalia.browser.fix import (
    FIX_SCHEMA,
    SYSTEM,
    Cell,
    FixRequest,
    NotebookFixer,
    build_user_text,
    parse_fix,
    parse_request,
)


def request(**over) -> dict:
    base = {
        "path": "work/control.ipynb",
        "kernel": "Python 3.13 (Conda)",
        "cells": [
            {"kind": "markdown", "source": "# Utilities"},
            {"kind": "code", "source": "import numpy as np\nimport qutip as qt"},
            {"kind": "code", "source": "print(qt.basis(2, 0))"},
        ],
        "failing": 1,
        "ename": "ModuleNotFoundError",
        "evalue": "No module named 'qutip'",
        "traceback": "Cell In[1], line 2\n----> 2 import qutip as qt\nModuleNotFoundError: No module named 'qutip'",
    }
    return {**base, **over}


def reply(kind="insert_before", source="%pip install qutip", summary="qutip isn't installed.") -> str:
    fix = {"kind": kind, "source": source}
    return json.dumps({"summary": summary, "explanation": "Install it in this kernel.", "fix": fix})


def test_parse_request_reads_what_the_panel_sends():
    req = parse_request(request())
    assert req.failing == 1
    assert req.cells[1] == Cell(1, "code", "import numpy as np\nimport qutip as qt")
    assert req.kernel == "Python 3.13 (Conda)"


@pytest.mark.parametrize(
    "bad",
    [None, request(cells=[]), request(failing=3), request(failing=True), request(ename=None), request(cells=["x"])],
)
def test_parse_request_rejects_what_it_cannot_use(bad):
    with pytest.raises(ValueError):
        parse_request(bad)


def test_context_marks_the_failing_cell_and_keeps_order():
    text = build_user_text(parse_request(request()))
    assert 'number="2" type="code" failing="true"' in text
    assert text.index("# Utilities") < text.index("import qutip") < text.index("qt.basis")
    assert "<traceback>" in text and "Cell 2 of 3 raised ModuleNotFoundError" in text


def test_context_keeps_the_nearest_cells_when_it_must_cut():
    cells = tuple(Cell(i, "code", f"cell{i}=" + "x" * 1000) for i in range(30))
    req = FixRequest("n.ipynb", None, cells, 15, "E", "", "tb")
    text = build_user_text(req, budget=5_500)
    assert "cell15=" in text and "cell14=" in text and "cell16=" in text
    assert "cell0=" not in text and "cell29=" not in text
    assert "cells left out for length" in text


def test_request_shape(cfg):
    client, messages = fake_client(reply())
    NotebookFixer(cfg, "key", client=client).fix(parse_request(request()))
    sent = messages.requests[0]
    assert sent["model"] == "claude-opus-5-5"
    assert sent["output_config"]["format"]["schema"] == FIX_SCHEMA
    assert sent["system"][0]["text"] == SYSTEM
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_returns_the_fix(cfg):
    client, _ = fake_client(reply())
    fix = NotebookFixer(cfg, "key", client=client).fix(parse_request(request()))
    assert (fix.kind, fix.source, fix.summary) == ("insert_before", "%pip install qutip", "qutip isn't installed.")
    assert fix.as_message()["fix"] == {"kind": "insert_before", "source": "%pip install qutip"}


def test_an_empty_change_is_no_change():
    assert parse_fix(reply(kind="replace", source="  "), "m").kind == "none"
    assert parse_fix(reply(kind="none", source="ignored"), "m").source == ""


ODD_KIND = json.dumps({"summary": "s", "explanation": "e", "fix": {"kind": "rewrite", "source": ""}})


@pytest.mark.parametrize("raw", ["not json", "{}", ODD_KIND])
def test_an_odd_reply_says_try_again(raw):
    with pytest.raises(BrainError) as e:
        parse_fix(raw, "m")
    assert e.value.action == "retry"


def test_no_key_points_to_settings(cfg):
    with pytest.raises(BrainError) as e:
        NotebookFixer(cfg, None).fix(parse_request(request()))
    assert e.value.action == "settings"


def test_api_errors_read_like_the_desktop_app(cfg):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.AuthenticationError("bad", response=httpx2.Response(401, request=req), body=None)
    client, _ = fake_client(error=err)
    with pytest.raises(BrainError, match="key was rejected"):
        NotebookFixer(cfg, "key", client=client).fix(parse_request(request()))


@pytest.mark.parametrize(("stop", "words"), [("refusal", "declined"), ("max_tokens", "cut off")])
def test_a_reply_that_did_not_finish_says_why(cfg, stop, words):
    client, _ = fake_client(reply(), stop_reason=stop)
    with pytest.raises(BrainError, match=words):
        NotebookFixer(cfg, "key", client=client).fix(parse_request(request()))
