"""Logging: readable console lines, JSON lines in a rotating file."""

import json
import logging

from marginalia.logs import FILE_NAME, setup_logging

log = logging.getLogger("marginalia.test")


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_file_gets_json_lines_with_extra_fields(tmp_path):
    path = setup_logging(tmp_path)
    log.info("answered %s", "q", extra={"model": "claude-opus-5-5", "seconds": 2.5})
    [rec] = [r for r in lines(path) if r["msg"] == "answered q"]
    assert rec["level"] == "INFO" and rec["logger"] == "marginalia.test"
    assert rec["model"] == "claude-opus-5-5" and rec["seconds"] == 2.5
    assert rec["ts"].endswith("+00:00")


def test_file_keeps_debug_even_when_the_console_is_quieter(tmp_path, capsys):
    path = setup_logging(tmp_path, level="WARNING")
    log.debug("detail")
    assert "detail" not in capsys.readouterr().out
    assert any(r["msg"] == "detail" for r in lines(path))


def test_console_lines_are_short_and_prefixed(tmp_path, capsys):
    setup_logging(None)
    log.info("Ready")
    assert capsys.readouterr().out == "[marginalia] Ready\n"


def test_exceptions_carry_their_traceback(tmp_path):
    path = setup_logging(tmp_path)
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("failed")
    [rec] = [r for r in lines(path) if r["msg"] == "failed"]
    assert "ValueError: boom" in rec["exc"]


def test_setting_up_again_replaces_the_handlers(tmp_path, capsys):
    setup_logging(tmp_path)
    setup_logging(tmp_path)
    log.info("once")
    assert capsys.readouterr().out.count("once") == 1


def test_an_unwritable_log_folder_is_reported_not_raised(tmp_path, caplog):
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    assert setup_logging(blocker) is None
    assert "Could not open the log file" in caplog.text
    assert FILE_NAME in caplog.text
