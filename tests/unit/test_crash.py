"""Crash reports: written locally, fatal dumps collected, offered as a pre-filled issue."""

import json
import sys
import threading
from urllib.parse import parse_qs, urlparse

import pytest

from marginalia.crash import MAX_URL_BODY, CrashReporter, issue_body, issue_url


@pytest.fixture
def reporter(tmp_path):
    r = CrashReporter(tmp_path)
    r.install()
    yield r
    r.uninstall()


def boom():
    raise ValueError("the matrix is singular")


def test_an_uncaught_exception_becomes_a_report(reporter, tmp_path, caplog):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "marginalia.jsonl").write_text('{"msg": "answered"}\n')
    try:
        boom()
    except ValueError:
        sys.excepthook(*sys.exc_info())
    [(path, report)] = reporter.pending()
    assert report["type"] == "ValueError" and report["message"] == "the matrix is singular"
    assert "boom" in report["traceback"] and report["where"] == "main thread"
    assert report["log_tail"] == ['{"msg": "answered"}']
    assert report["version"] and report["python"] and not report["handled"]
    assert "Unexpected error" in caplog.text


def test_a_worker_thread_exception_is_recorded_too(reporter):
    t = threading.Thread(target=boom, name="worker-1")
    t.start()
    t.join()
    [(_, report)] = reporter.pending()
    assert report["where"] == "thread worker-1"


def test_ctrl_c_is_not_a_crash(reporter, monkeypatch):
    seen = []
    monkeypatch.setattr(sys, "__excepthook__", lambda *a: seen.append(a[0]))
    sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    assert reporter.pending() == [] and seen == [KeyboardInterrupt]


def test_a_fatal_dump_from_last_run_is_collected_once(tmp_path):
    r = CrashReporter(tmp_path)
    r.dir.mkdir(parents=True)
    r.fatal_path.write_text("Fatal Python error: Segmentation fault\n\nCurrent thread 0x1 (most recent call first):\n")
    path = r.collect_fatal()
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["type"] == "Fatal error" and "Segmentation fault" in report["message"]
    assert r.collect_fatal() is None, "the dump is cleared once collected"


def test_handled_reports_are_not_offered_again(reporter):
    try:
        boom()
    except ValueError:
        sys.excepthook(*sys.exc_info())
    [(path, _)] = reporter.pending()
    reporter.mark_handled(path)
    assert reporter.pending() == []


def test_uninstall_restores_the_hooks(tmp_path):
    before = (sys.excepthook, threading.excepthook)
    r = CrashReporter(tmp_path)
    r.install()
    assert sys.excepthook != before[0]
    r.uninstall()
    assert (sys.excepthook, threading.excepthook) == before


REPORT = {
    "version": "0.2.0",
    "platform": "macOS-26.6",
    "python": "3.12.12",
    "qt": "6.11.2",
    "frozen": True,
    "where": "main thread",
    "type": "ValueError",
    "message": "the matrix is singular",
    "traceback": "Traceback (most recent call last):\n  ...\nValueError: the matrix is singular",
    "log_tail": ['{"msg": "answered"}'],
}


def test_issue_url_is_prefilled_and_labelled():
    url = urlparse(issue_url(REPORT, base="https://github.com/o/r/issues/new"))
    q = parse_qs(url.query)
    assert url.path == "/o/r/issues/new"
    assert q["title"] == ["Crash: ValueError: the matrix is singular"] and q["labels"] == ["crash"]
    body = q["body"][0]
    assert "What were you doing" in body and "packaged app" in body and "ValueError" in body


def test_a_huge_traceback_is_cut_to_fit_a_url():
    body = issue_body({**REPORT, "traceback": "x" * 50_000})
    assert len(body) < MAX_URL_BODY + 100 and "full report is in your crashes folder" in body
