"""Settings, read from environment variables (and from a .env file if python-dotenv is installed)."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import find_dotenv, load_dotenv

    # The folder you start from first, then the folders above the package (an editable checkout).
    load_dotenv(find_dotenv(usecwd=True)) or load_dotenv()
except ImportError:
    pass


DEFAULT_CONTEXT = (
    "The user is a graduate researcher in quantum information (quantum error correction "
    "and quantum machine learning). They read papers and watch lectures and want precise, "
    "technical answers that respect the notation on their screen."
)


log = logging.getLogger(__name__)

EFFORTS = ("low", "medium", "high", "xhigh", "max")
LOG_LEVELS = ("debug", "info", "warning", "error")


def _warn(message: str) -> None:
    log.warning(message)


def _number(name: str, default: int) -> int:
    value = os.environ.get(name)
    try:
        return default if value is None else int(value)
    except ValueError:
        _warn(f"{name}={value!r} is not a whole number; using {default}.")
        return default


def _choice(name: str, default: str, allowed: tuple[str, ...]) -> str:
    value = os.environ.get(name, default).strip().lower()
    if value not in allowed:
        _warn(f"{name}={value!r} is not one of {', '.join(allowed)}; using {default}.")
        return default
    return value


def _flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    api_key: str | None
    model: str
    hires: bool
    hotkey: str
    hotkey_enabled: bool
    ocr_enabled: bool
    log_dir: Path
    demo: bool
    user_context: str
    max_tokens: int
    effort: str
    voice_enabled: bool
    whisper_model: str
    save_cases: bool = False
    log_level: str = "info"


def load_config(demo: bool = False, no_hotkey: bool = False, no_ocr: bool = False, no_voice: bool = False) -> Config:
    return Config(
        api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        model=os.environ.get("MARGINALIA_MODEL", "claude-opus-5-5"),
        # Set to 1 only for models on the high-resolution image tier (sharper small text).
        hires=_flag("MARGINALIA_HIRES"),
        hotkey=os.environ.get("MARGINALIA_HOTKEY", "<ctrl>+<alt>+<space>"),
        hotkey_enabled=(not no_hotkey) and _flag("MARGINALIA_HOTKEY_ENABLED", True),
        ocr_enabled=(not no_ocr) and _flag("MARGINALIA_OCR", True),
        log_dir=Path(os.environ.get("MARGINALIA_LOG_DIR", str(Path.home() / "Marginalia"))).expanduser(),
        demo=demo or _flag("MARGINALIA_DEMO"),
        user_context=os.environ.get("MARGINALIA_USER_CONTEXT", DEFAULT_CONTEXT),
        # Thinking shares this budget on current models, so keep it generous; answers stay short anyway.
        max_tokens=_number("MARGINALIA_MAX_TOKENS", 16000),
        # low | medium | high | xhigh | max. Trades answer depth against wait time.
        effort=_choice("MARGINALIA_EFFORT", "medium", EFFORTS),
        voice_enabled=(not no_voice) and _flag("MARGINALIA_VOICE", True),
        # Whisper size: tiny.en, base.en, small.en (sharper, slower). Downloaded once on first use.
        whisper_model=os.environ.get("MARGINALIA_WHISPER_MODEL", "base.en"),
        # Also save each question as an unlabelled eval case (raw screenshot + case.json) under
        # <log dir>/cases. Off by default: full-resolution screenshots add up, and may be private.
        save_cases=_flag("MARGINALIA_SAVE_CASES"),
        # Console detail. The log file (<log dir>/logs/marginalia.jsonl) always keeps everything.
        log_level=_choice("MARGINALIA_LOG_LEVEL", "info", LOG_LEVELS),
    )
