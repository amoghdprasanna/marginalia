"""Shared fixtures. Qt runs offscreen so the suite needs no display (CI, SSH, headless Linux)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from marginalia.config import Config  # noqa: E402


@pytest.fixture
def cfg(tmp_path) -> Config:
    return Config(
        api_key="test-key",
        model="claude-opus-5",
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
