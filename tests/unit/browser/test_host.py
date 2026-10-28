"""The helper's request loop, over in-memory pipes."""
import io

from helpers import fake_client
from test_fix import reply, request

from marginalia.browser.fix import NotebookFixer
from marginalia.browser.framing import read_message, write_message
from marginalia.browser.host import handle, serve


def run(messages, fixer):
    stdin = io.BytesIO()
    for m in messages:
        write_message(stdin, m)
    stdin.seek(0)
    stdout = io.BytesIO()
    code = serve(stdin, stdout, fixer)
    stdout.seek(0)
    out = []
    while (m := read_message(stdout)) is not None:
        out.append(m)
    return code, out


def make_fixer(cfg, text=None, calls=None):
    client, messages = fake_client(text or reply())

    def fixer():
        if calls is not None:
            calls.append(1)
        about = {"model": cfg.model, "modelName": "Claude Opus 5.5", "hasKey": True}
        return NotebookFixer(cfg, "key", client=client), about

    return fixer, messages


def test_hello_says_which_model_and_whether_there_is_a_key(cfg):
    fixer, _ = make_fixer(cfg)
    code, out = run([{"id": 1, "type": "hello"}], fixer)
    assert code == 0
    assert out[0]["id"] == 1 and out[0]["type"] == "hello"
    assert out[0]["modelName"] == "Claude Opus 5.5" and out[0]["hasKey"] is True


def test_fix_answers_with_the_same_id(cfg):
    fixer, messages = make_fixer(cfg)
    _, out = run([{"id": "a", "type": "fix", "request": request()}], fixer)
    assert out == [
        {
            "id": "a",
            "type": "fix",
            "summary": "qutip isn't installed.",
            "explanation": "Install it in this kernel.",
            "fix": {"kind": "insert_before", "source": "%pip install qutip"},
            "model": "claude-opus-5-5",
        }
    ]
    assert len(messages.requests) == 1


def test_settings_are_read_once_per_session(cfg):
    calls: list[int] = []
    fixer, _ = make_fixer(cfg, calls=calls)
    run([{"id": 1, "type": "hello"}, {"id": 2, "type": "fix", "request": request()}], fixer)
    assert calls == [1]


def test_every_failure_is_an_answer(cfg):
    fixer, _ = make_fixer(cfg, text="nonsense")
    assert handle({"id": 3, "type": "fix", "request": request()}, fixer)["type"] == "error"
    assert "bad request" in handle({"id": 4, "type": "fix", "request": {}}, fixer)["message"]
    assert handle({"id": 5, "type": "dance"}, fixer)["type"] == "error"
    assert handle("hi", fixer)["type"] == "error"

    def broken():
        raise RuntimeError("keychain exploded")

    assert handle({"id": 6, "type": "hello"}, broken)["message"].startswith("Marginalia's helper hit a problem")


def test_stops_on_a_garbled_stream(cfg):
    fixer, _ = make_fixer(cfg)
    stdout = io.BytesIO()
    assert serve(io.BytesIO(b"\x01\x00"), stdout, fixer) == 1
    assert stdout.getvalue() == b""
