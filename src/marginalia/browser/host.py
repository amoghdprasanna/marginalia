"""The browser helper Chrome starts for the notebook extension (ADR 0030).

Chrome runs it when the panel connects and closes its stdin when the panel goes; it answers one
request at a time over native messaging. It reads Marginalia's settings and the Claude key from
the keychain, so no key ever lives in the browser. stdout carries the protocol, so nothing else
may print to it.

Requests are `{"id": ..., "type": "hello" | "fix", ...}`; every reply carries the same id.
"""
from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import Any, BinaryIO

from .. import __version__
from ..brain.types import BrainError
from .fix import NotebookFixer, parse_request
from .framing import FramingError, read_message, write_message

log = logging.getLogger(__name__)

PROTOCOL = 1


def claude_fixer() -> tuple[NotebookFixer, dict[str, Any]]:
    """A fixer from Marginalia's own settings, and what the panel shows about it."""
    from ..config import find_key, load_config
    from ..providers import PROVIDERS, model_name, provider_of_model
    from ..secrets import Keychain

    cfg = load_config()
    # Fix is Claude-only for now (ADR 0030): keep your model if it's a Claude one.
    if provider_of_model(cfg.model) != "anthropic":
        cfg.model = PROVIDERS["anthropic"].default_model
    key, source = find_key("anthropic", Keychain())
    about = {"model": cfg.model, "modelName": model_name(cfg.model), "hasKey": key is not None, "keySource": source}
    return NotebookFixer(cfg, key), about


def handle(message: Any, fixer: Callable[[], tuple[NotebookFixer, dict[str, Any]]]) -> dict[str, Any]:
    """One request -> its reply. Never raises: every failure is an error reply with a sentence."""
    if not isinstance(message, dict) or not isinstance(message.get("id"), (str, int)):
        return {"type": "error", "message": "Marginalia's helper got a request it doesn't understand."}
    reply_id = message["id"]
    kind = message.get("type")
    try:
        if kind == "hello":
            _, about = fixer()
            return {"id": reply_id, "type": "hello", "protocol": PROTOCOL, "version": __version__, **about}
        if kind == "fix":
            req = parse_request(message.get("request"))
            fx, _ = fixer()
            return {"id": reply_id, "type": "fix", **fx.fix(req).as_message()}
        return {"id": reply_id, "type": "error", "message": f"Unknown request {kind!r}."}
    except ValueError as exc:
        return {"id": reply_id, "type": "error", "message": f"The panel sent a bad request: {exc}"}
    except BrainError as exc:
        return {"id": reply_id, "type": "error", "message": str(exc), "action": exc.action}
    except Exception:  # the panel must always get an answer
        log.exception("fix failed")
        return {"id": reply_id, "type": "error", "message": "Marginalia's helper hit a problem. Try again."}


def serve(stdin: BinaryIO, stdout: BinaryIO, fixer=claude_fixer) -> int:
    """Answer requests until Chrome closes the pipe. Settings are read once, on first use."""
    cached: list[tuple[NotebookFixer, dict[str, Any]]] = []

    def once() -> tuple[NotebookFixer, dict[str, Any]]:
        if not cached:
            cached.append(fixer())
        return cached[0]

    while True:
        try:
            message = read_message(stdin)
        except FramingError as exc:
            log.error("bad message from Chrome: %s", exc)
            return 1
        if message is None:
            return 0
        write_message(stdout, handle(message, once))


def main() -> int:
    """Chrome passes the caller's origin (`chrome-extension://<id>/`); `install` and `uninstall`
    set the helper up for this browser instead."""
    args = sys.argv[1:]
    if args[:1] in (["install"], ["uninstall"]):
        from .install import cli

        return cli(args[0])
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    sys.stdout = sys.stderr  # a stray print must never corrupt a message
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="marginalia-helper %(levelname)s %(message)s")
    return serve(stdin, stdout)


if __name__ == "__main__":
    raise SystemExit(main())
