"""Shared fixtures. Qt runs offscreen so the suite needs no display (CI, SSH, headless Linux).

Layout, and the marker each folder gets automatically:
  unit/         pure logic, no Qt event loop          -m unit   (fast; run while editing)
  ui/           one widget at a time, pytest-qt        -m ui
  integration/  the controller with every service faked  -m integration
"""

import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from marginalia.config import Config  # noqa: E402


@pytest.fixture
def cfg(tmp_path) -> Config:
    return Config(
        api_key="test-key",
        model="claude-opus-5-5",
        hires=False,
        hotkey="<ctrl>+<alt>+<space>",
        hotkey_enabled=False,
        ocr_enabled=False,
        log_dir=tmp_path,
        demo=False,
        user_context="The user studies quantum error correction.",
        max_tokens=16000,
        effort="medium",
        voice_enabled=False,
        whisper_model="tiny.en",
    )


@pytest.fixture(autouse=True)
def _log_everything(caplog):
    """App messages are logged, not printed; let every test see them in caplog.text.

    Afterwards, drop handlers a test's setup_logging() added: they hold that test's stdout and log file.
    """
    caplog.set_level(logging.DEBUG, logger="marginalia")
    yield
    logger = logging.getLogger("marginalia")
    for h in [h for h in logger.handlers if getattr(h, "_marginalia", False)]:
        logger.removeHandler(h)
        h.close()


LAYERS = ("unit", "ui", "integration")


def pytest_collection_modifyitems(config, items):
    for item in items:
        parts = Path(str(item.fspath)).parts
        layer = next((p for p in LAYERS if p in parts), None)
        if layer:
            item.add_marker(layer)
        if layer in ("ui", "integration"):
            item.add_marker("qt")
