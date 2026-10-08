"""Settings: defaults, then the settings file (written by the Settings window), then environment
variables (and a .env file if python-dotenv is installed), then command-line switches.

Each layer overrides the one before (ADR 0015). `Config.sources` says where each value came
from, so the Settings window can show which fields an environment variable is pinning.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from dotenv import find_dotenv, load_dotenv

    # The folder you start from first, then the folders above the package (an editable checkout).
    load_dotenv(find_dotenv(usecwd=True)) or load_dotenv()
except ImportError:
    pass

log = logging.getLogger(__name__)

DEFAULT_CONTEXT = (
    "The user is a graduate researcher in quantum information (quantum error correction "
    "and quantum machine learning). They read papers and watch lectures and want precise, "
    "technical answers that respect the notation on their screen."
)
EFFORTS = ("low", "medium", "high", "xhigh", "max")
LOG_LEVELS = ("debug", "info", "warning", "error")
# Suggestions for the Settings window; any faster-whisper model name works.
WHISPER_MODELS = ("tiny.en", "base.en", "small.en", "medium.en", "large-v3")
TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Setting:
    """One user-facing setting: its Config field, environment variable, type and default."""

    key: str
    env: str
    kind: type
    default: Any
    choices: tuple[str, ...] | None = None


SETTINGS: tuple[Setting, ...] = (
    Setting("model", "MARGINALIA_MODEL", str, "claude-opus-5-5"),
    # low | medium | high | xhigh | max. Trades answer depth against wait time.
    Setting("effort", "MARGINALIA_EFFORT", str, "medium", EFFORTS),
    # Only for models on the high-resolution image tier (sharper small text).
    Setting("hires", "MARGINALIA_HIRES", bool, False),
    Setting("hotkey", "MARGINALIA_HOTKEY", str, "<ctrl>+<alt>+<space>"),
    Setting("hotkey_enabled", "MARGINALIA_HOTKEY_ENABLED", bool, True),
    # Hold to talk; a quick tap listens until you pause instead (ADR 0017).
    Setting("voice_hotkey", "MARGINALIA_VOICE_HOTKEY", str, "<ctrl>+<alt>+v"),
    Setting("ocr_enabled", "MARGINALIA_OCR", bool, True),
    Setting("voice_enabled", "MARGINALIA_VOICE", bool, True),
    # Whisper size: tiny.en, base.en, small.en (sharper, slower). Downloaded once on first use.
    Setting("whisper_model", "MARGINALIA_WHISPER_MODEL", str, "base.en"),
    Setting("user_context", "MARGINALIA_USER_CONTEXT", str, DEFAULT_CONTEXT),
    Setting("log_dir", "MARGINALIA_LOG_DIR", Path, Path.home() / "Marginalia"),
    # Thinking shares this budget on current models, so keep it generous; answers stay short anyway.
    Setting("max_tokens", "MARGINALIA_MAX_TOKENS", int, 16000),
    # Also save each question as an unlabelled eval case (raw screenshot + case.json) under
    # <log dir>/cases. Off by default: full-resolution screenshots add up, and may be private.
    Setting("save_cases", "MARGINALIA_SAVE_CASES", bool, False),
    # Console detail. The log file (<log dir>/logs/marginalia.jsonl) always keeps everything.
    Setting("log_level", "MARGINALIA_LOG_LEVEL", str, "info", LOG_LEVELS),
    Setting("demo", "MARGINALIA_DEMO", bool, False),
)
BY_KEY = {s.key: s for s in SETTINGS}


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
    voice_hotkey: str = "<ctrl>+<alt>+v"
    # Where each value came from: "default", "settings", "env" or "command line" (plus "keychain"
    # for the API key). Lets the Settings window lock fields that an environment variable pins.
    sources: dict[str, str] = field(default_factory=dict)


# the settings file ----------------------------------------------------------------------------


def settings_path() -> Path:
    """Where the Settings window saves: the platform's per-user config folder."""
    override = os.environ.get("MARGINALIA_SETTINGS_FILE")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Marginalia"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Marginalia"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "marginalia"
    return base / "settings.json"


class SettingsStore:
    """The settings file: a flat JSON object of setting keys. Unknown keys are kept, not lost."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else settings_path()

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            log.warning("Ignoring the settings file %s: %s", self.path, exc)
            return {}
        if not isinstance(data, dict):
            log.warning("Ignoring the settings file %s: not a JSON object", self.path)
            return {}
        return data

    def save(self, values: dict[str, Any]) -> None:
        """Merge `values` into the file. Written to a temporary file first, so a crash can't leave half a file."""
        data = self.load()
        data.update({k: str(v) if isinstance(v, Path) else v for k, v in values.items()})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def first_run(self) -> bool:
        return not self.path.exists()


# resolving values ----------------------------------------------------------------------------


def _warn(message: str) -> None:
    log.warning(message)


def parse(s: Setting, raw: Any, where: str) -> Any:
    """Turn a raw value (a string from the environment, or JSON) into the setting's type.

    A value that doesn't fit falls back to the default with a warning naming where it came from,
    rather than stopping the app (a typo in an effort level used to fail every question).
    """
    try:
        if s.kind is bool:
            value = raw if isinstance(raw, bool) else str(raw).strip().lower() in TRUE
        elif s.kind is int:
            if isinstance(raw, bool):
                raise ValueError
            value = int(raw)
        elif s.kind is Path:
            value = Path(str(raw)).expanduser()
        else:
            value = str(raw).strip().lower() if s.choices is not None else str(raw)
    except (TypeError, ValueError):
        _warn(f"{where}={raw!r} is not a {'whole number' if s.kind is int else s.kind.__name__}; using {s.default}.")
        return s.default
    if s.choices is not None and value not in s.choices:
        _warn(f"{where}={raw!r} is not one of {', '.join(s.choices)}; using {s.default}.")
        return s.default
    return value


def resolve(stored: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Every setting's value and its source: environment over settings file over default."""
    values, sources = {}, {}
    for s in SETTINGS:
        if os.environ.get(s.env) is not None:
            values[s.key], sources[s.key] = parse(s, os.environ[s.env], s.env), "env"
        elif s.key in stored:
            values[s.key], sources[s.key] = parse(s, stored[s.key], f"settings {s.key}"), "settings"
        else:
            values[s.key], sources[s.key] = s.default, "default"
    return values, sources


def load_config(
    demo: bool = False,
    no_hotkey: bool = False,
    no_ocr: bool = False,
    no_voice: bool = False,
    store: SettingsStore | None = None,
    keychain=None,
) -> Config:
    """Read every layer. `store` and `keychain` are injectable so tests touch neither the real
    settings file nor the real keychain."""
    store = store if store is not None else SettingsStore()
    values, sources = resolve(store.load())
    for flag, key, value in (
        (demo, "demo", True),
        (no_hotkey, "hotkey_enabled", False),
        (no_ocr, "ocr_enabled", False),
        (no_voice, "voice_enabled", False),
    ):
        if flag:
            values[key], sources[key] = value, "command line"

    api_key = os.environ.get("ANTHROPIC_API_KEY") or None
    sources["api_key"] = "env" if api_key else "none"
    if api_key is None:
        if keychain is None:
            from .secrets import Keychain

            keychain = Keychain()
        api_key = keychain.get()
        if api_key:
            sources["api_key"] = "keychain"
    return Config(api_key=api_key, sources=sources, **values)
