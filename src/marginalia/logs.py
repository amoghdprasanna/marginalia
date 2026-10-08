"""Logging: short readable lines on the console, JSON lines in a file you can attach to a bug report.

Every module logs through `logging.getLogger(__name__)`, so all records sit under the
"marginalia" logger. Pass structured fields with `extra=`; they land as keys in the JSON line:

    log.info("answered", extra={"model": "claude-opus-5-5", "seconds": 3.2})
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = "marginalia"
CONSOLE_FORMAT = "[marginalia] %(message)s"
FILE_NAME = "marginalia.jsonl"
MAX_BYTES = 1_000_000  # per file; with BACKUPS that caps the logs at a few MB
BACKUPS = 3

# Attributes every LogRecord has; anything else on a record came from `extra=`.
_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line: time, level, logger, message, then any `extra=` fields."""

    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        out.update({k: v for k, v in vars(record).items() if k not in _STANDARD and not k.startswith("_")})
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str, ensure_ascii=False)


def _ours(handler: logging.Handler) -> bool:
    return getattr(handler, "_marginalia", False)


def setup_logging(log_dir: Path | None = None, level: int | str = logging.INFO) -> Path | None:
    """Console at `level`; with `log_dir`, also every DEBUG+ record as JSON in <log_dir>/logs/.

    Safe to call again (main calls it once before the config is read, once after): it replaces
    the handlers it added before. Returns the log file, or None when there is none.
    """
    logger = logging.getLogger(ROOT)
    logger.setLevel(logging.DEBUG)
    for h in [h for h in logger.handlers if _ours(h)]:
        logger.removeHandler(h)
        h.close()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(CONSOLE_FORMAT))
    console._marginalia = True
    logger.addHandler(console)

    if log_dir is None:
        return None
    path = Path(log_dir) / "logs" / FILE_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file = logging.handlers.RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not open the log file %s: %s", path, exc)
        return None
    file.setLevel(logging.DEBUG)
    file.setFormatter(JsonFormatter())
    file._marginalia = True
    logger.addHandler(file)
    return path
