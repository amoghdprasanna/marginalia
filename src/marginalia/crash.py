"""Crash reports: always written locally, offered for sending only if you opt in (ADR 0020).

    Python exceptions that nothing caught (main thread, worker threads, Qt slots) and fatal
    errors (a segfault in Qt or ctypes, via faulthandler) become JSON reports in
    <log dir>/crashes/. With "Offer to report crashes" on, the next launch asks whether to open a
    pre-filled GitHub issue with one; you see exactly what would be sent before sending it.
"""
from __future__ import annotations

import faulthandler
import json
import logging
import platform
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from . import ISSUES_URL, __version__

log = logging.getLogger(__name__)

LOG_TAIL = 40  # lines of the JSON log to attach (they hold metrics, never question text)
MAX_URL_BODY = 6000  # browsers and GitHub cap URL length; the rest is in the local file


class CrashReporter:
    def __init__(self, log_dir: Path) -> None:
        self.dir = Path(log_dir) / "crashes"
        self.log_file = Path(log_dir) / "logs" / "marginalia.jsonl"
        self.fatal_path = self.dir / "fatal.log"
        self._fatal_file = None
        self._previous: tuple = ()

    # catching ---------------------------------------------------------------------------------

    def install(self) -> None:
        """Hook uncaught exceptions on every thread, and fatal signals."""
        self.dir.mkdir(parents=True, exist_ok=True)
        self._previous = (sys.excepthook, threading.excepthook)
        sys.excepthook = self._sys_hook
        threading.excepthook = self._thread_hook
        try:
            self._fatal_file = self.fatal_path.open("a", encoding="utf-8")
            faulthandler.enable(self._fatal_file)
        except OSError as exc:
            log.warning("Fatal errors won't be recorded: %s", exc)

    def uninstall(self) -> None:
        if self._previous:
            sys.excepthook, threading.excepthook = self._previous
            self._previous = ()
        if self._fatal_file is not None:
            faulthandler.disable()
            self._fatal_file.close()
            self._fatal_file = None

    def _sys_hook(self, exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            return sys.__excepthook__(exc_type, exc, tb)
        self.record(exc_type, exc, tb, "main thread")
        log.error("Unexpected error", exc_info=(exc_type, exc, tb))

    def _thread_hook(self, args) -> None:
        where = f"thread {args.thread.name}" if args.thread else "a thread"
        self.record(args.exc_type, args.exc_value, args.exc_traceback, where)
        log.error("Unexpected error in %s", where, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    # writing ----------------------------------------------------------------------------------

    def _log_tail(self) -> list[str]:
        try:
            return self.log_file.read_text(encoding="utf-8").splitlines()[-LOG_TAIL:]
        except OSError:
            return []

    def _write(self, report: dict) -> Path | None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = self.dir / f"{stamp}.json"
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return path
        except OSError as exc:
            log.warning("Could not write a crash report: %s", exc)
            return None

    def _base(self) -> dict:
        try:
            from PySide6 import __version__ as qt
        except ImportError:  # pragma: no cover
            qt = "?"
        return {
            "time": datetime.now().isoformat(timespec="seconds"),
            "version": __version__,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "qt": qt,
            "frozen": bool(getattr(sys, "frozen", False)),
            "handled": False,
        }

    def record(self, exc_type, exc, tb, where: str) -> Path | None:
        return self._write(
            {
                **self._base(),
                "where": where,
                "type": getattr(exc_type, "__name__", str(exc_type)),
                "message": str(exc)[:500],
                "traceback": "".join(traceback.format_exception(exc_type, exc, tb)),
                "log_tail": self._log_tail(),
            }
        )

    def collect_fatal(self) -> Path | None:
        """A fatal error last run left a dump in fatal.log; turn it into a report and clear it."""
        try:
            text = self.fatal_path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return None
        if not text:
            return None
        if self._fatal_file is not None:
            self._fatal_file.truncate(0)
        else:
            self.fatal_path.write_text("", encoding="utf-8")
        return self._write(
            {
                **self._base(),
                "where": "fatal error (the app closed)",
                "type": "Fatal error",
                "message": text.splitlines()[0][:500],
                "traceback": text,
                "log_tail": self._log_tail(),
            }
        )

    # offering ---------------------------------------------------------------------------------

    def pending(self) -> list[tuple[Path, dict]]:
        """Reports not yet offered, oldest first."""
        out = []
        for path in sorted(self.dir.glob("*.json")) if self.dir.exists() else []:
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not report.get("handled"):
                out.append((path, report))
        return out

    def mark_handled(self, path: Path) -> None:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            report["handled"] = True
            path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except (OSError, ValueError) as exc:
            log.debug("Could not mark %s handled: %s", path, exc)


def issue_body(report: dict) -> str:
    lines = [
        "**What were you doing when it happened?**",
        "",
        "",
        "---",
        f"Marginalia {report.get('version')} on {report.get('platform')}, Python {report.get('python')}, "
        f"Qt {report.get('qt')}{', packaged app' if report.get('frozen') else ''}",
        f"Where: {report.get('where')}",
        "",
        "```",
        report.get("traceback", "").strip(),
        "```",
    ]
    if report.get("log_tail"):
        lines += ["", "<details><summary>Recent log</summary>", "", "```", *report["log_tail"], "```", "</details>"]
    body = "\n".join(lines)
    if len(body) > MAX_URL_BODY:
        body = body[:MAX_URL_BODY] + "\n…(cut; the full report is in your crashes folder)\n```"
    return body


def issue_url(report: dict, base: str = ISSUES_URL) -> str:
    title = f"Crash: {report.get('type')}: {report.get('message', '')}"[:120]
    return f"{base}?{urlencode({'title': title, 'body': issue_body(report), 'labels': 'crash'})}"
