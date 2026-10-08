"""The Settings window: everything that used to need a .env file, plus the API key in the keychain.

It edits a copy of the values and writes the settings file only on Save; the controller then
reloads the config and applies what changed (ADR 0015). Fields an environment variable pins
are shown but locked, with the variable's name, so an edit is never silently ignored.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import BY_KEY, EFFORTS, LOG_LEVELS, WHISPER_MODELS, Config, SettingsStore
from ..hotkeys import Combo, format_combo, parse_combo, to_text
from ..secrets import Keychain, mask
from .theme import DIALOG_STYLE, bring_to_front

MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1")

# Qt key -> our key name, for keys whose name isn't their ASCII character.
_QT_KEYS = {
    Qt.Key_Space: "space", Qt.Key_Return: "enter", Qt.Key_Enter: "enter", Qt.Key_Tab: "tab",
    Qt.Key_Backspace: "backspace", Qt.Key_Delete: "delete", Qt.Key_Up: "up", Qt.Key_Down: "down",
    Qt.Key_Left: "left", Qt.Key_Right: "right", Qt.Key_Home: "home", Qt.Key_End: "end",
    Qt.Key_PageUp: "page_up", Qt.Key_PageDown: "page_down",
    **{getattr(Qt, f"Key_F{i}"): f"f{i}" for i in range(1, 13)},
}  # fmt: skip
_QT_MODIFIER_KEYS = {Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta, Qt.Key_AltGr}


def held_modifiers(mods, mac: bool = sys.platform == "darwin") -> frozenset[str]:
    """Qt's modifier flags -> our names. On macOS Qt calls Command "Control" and Control "Meta"."""
    held = set()
    if mods & Qt.ShiftModifier:
        held.add("shift")
    if mods & Qt.AltModifier:
        held.add("alt")
    if mods & Qt.ControlModifier:
        held.add("cmd" if mac else "ctrl")
    if mods & Qt.MetaModifier:
        held.add("ctrl" if mac else "cmd")
    return frozenset(held)


def combo_from_qt(key: int, mods, mac: bool = sys.platform == "darwin") -> Combo | None:
    """A key press as Qt reports it -> Combo, or None when it isn't a usable chord (yet)."""
    key = int(key)
    if key in _QT_KEYS:
        name = _QT_KEYS[key]
    elif 0x20 < key < 0x7F:
        name = chr(key).lower()
    else:
        return None
    held = held_modifiers(mods, mac)
    return Combo(held, name) if held else None


class HotkeyEdit(QLineEdit):
    """Click, then press the chord you want. Backspace clears (no hotkey); Esc keeps the old one."""

    changed = Signal()

    def __init__(self, value: str = "") -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setPlaceholderText("None (click, then press keys)")
        self.value = ""
        self._before = ""
        self.set_value(value)

    def set_value(self, text: str) -> None:
        self.value = text
        self.setText(format_combo(text) if text else "")

    def focusInEvent(self, e) -> None:  # noqa: N802
        self._before = self.value
        self.setText("Press the keys…")
        super().focusInEvent(e)

    def focusOutEvent(self, e) -> None:  # noqa: N802
        self.set_value(self.value)
        super().focusOutEvent(e)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        key, mods = e.key(), e.modifiers()
        bare = not (mods & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier | Qt.ShiftModifier))
        if key == Qt.Key_Escape and bare:
            self.set_value(self._before)
            self.clearFocus()
            return
        if key in (Qt.Key_Backspace, Qt.Key_Delete) and bare:
            self.set_value("")
            self.changed.emit()
            self.clearFocus()
            return
        if key in _QT_MODIFIER_KEYS:  # still choosing: show the modifiers held so far
            held = held_modifiers(mods)
            self.setText(format_combo(Combo(held, "x"))[:-1] + "…" if held else "Press the keys…")
            return
        combo = combo_from_qt(key, mods)
        if combo is None:
            self.setText("Hold a modifier (Ctrl, Alt, Shift, Cmd) too")
            return
        self.set_value(to_text(combo))
        self.changed.emit()
        self.clearFocus()


def _locked(widget: QWidget, setting_env: str) -> None:
    widget.setEnabled(False)
    widget.setToolTip(f"Set by {setting_env} in your environment or .env file; remove it there to edit here.")


class SettingsWindow(QWidget):
    """Edits settings; emits `saved` after writing them. The controller applies them."""

    saved = Signal()
    closed = Signal()

    def __init__(self, cfg: Config, store: SettingsStore, keychain: Keychain) -> None:
        super().__init__(None, Qt.Window)
        self.setWindowTitle("Marginalia Settings")
        self.setStyleSheet(DIALOG_STYLE)
        self.store, self.keychain = store, keychain
        self.fields: dict[str, QWidget] = {}
        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.hide()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)
        lay.addWidget(self._claude_group())
        lay.addWidget(self._keys_group())
        lay.addWidget(self._voice_group())
        lay.addWidget(self._journal_group())
        lay.addWidget(self.error)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.save_btn = QPushButton("Save")
        self.save_btn.setDefault(True)
        self.save_btn.setObjectName("primary")
        self.cancel_btn.clicked.connect(self.close)
        self.save_btn.clicked.connect(self.save)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.save_btn)
        lay.addLayout(buttons)
        self.setFixedWidth(560)
        self.load(cfg)

    # building ---------------------------------------------------------------------------------

    def _form(self, title: str) -> tuple[QGroupBox, QFormLayout]:
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        return box, form

    def _combo(self, key: str, items, editable: bool = False) -> QComboBox:
        w = QComboBox()
        w.addItems(list(items))
        w.setEditable(editable)
        self.fields[key] = w
        return w

    def _check(self, key: str, text: str) -> QCheckBox:
        w = QCheckBox(text)
        self.fields[key] = w
        return w

    def _claude_group(self) -> QGroupBox:
        box, form = self._form("Claude")
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Paste a new key to replace it")
        self.key_status = QLabel()
        self.key_status.setObjectName("muted")
        self.key_remove = QPushButton("Remove")
        self.key_remove.clicked.connect(self._remove_key)
        row = QHBoxLayout()
        row.addWidget(self.key_edit, 1)
        row.addWidget(self.key_remove)
        form.addRow("API key", row)
        form.addRow("", self.key_status)
        form.addRow("Model", self._combo("model", MODELS, editable=True))
        form.addRow("Effort", self._combo("effort", EFFORTS))
        context = QPlainTextEdit()
        context.setFixedHeight(64)
        self.fields["user_context"] = context
        form.addRow("About you", context)
        tokens = QSpinBox()
        tokens.setRange(1024, 128000)
        tokens.setSingleStep(1000)
        self.fields["max_tokens"] = tokens
        form.addRow("Max tokens", tokens)
        form.addRow("", self._check("hires", "High-resolution images (only for models on that tier)"))
        return box

    def _keys_group(self) -> QGroupBox:
        box, form = self._form("Shortcuts")
        form.addRow("", self._check("hotkey_enabled", "Use global shortcuts"))
        ask = HotkeyEdit()
        voice = HotkeyEdit()
        self.fields["hotkey"], self.fields["voice_hotkey"] = ask, voice
        form.addRow("Ask by typing", ask)
        form.addRow("Hold to talk", voice)
        return box

    def _voice_group(self) -> QGroupBox:
        box, form = self._form("Voice and reading")
        form.addRow("", self._check("voice_enabled", "Ask by voice (local Whisper)"))
        form.addRow("Speech model", self._combo("whisper_model", WHISPER_MODELS, editable=True))
        form.addRow("", self._check("ocr_enabled", "Read text on screen with OCR (sharper pointing)"))
        return box

    def _journal_group(self) -> QGroupBox:
        box, form = self._form("Journal, logs and updates")
        folder = QLineEdit()
        self.fields["log_dir"] = folder
        browse = QPushButton("Choose…")
        browse.clicked.connect(self._choose_folder)
        self.browse_btn = browse
        row = QHBoxLayout()
        row.addWidget(folder, 1)
        row.addWidget(browse)
        form.addRow("Folder", row)
        form.addRow("Console detail", self._combo("log_level", LOG_LEVELS))
        form.addRow("", self._check("save_cases", "Also save each question as an eval case"))
        form.addRow("", self._check("check_updates", "Check for new versions once a day"))
        form.addRow("", self._check("crash_reports", "Offer to report crashes (you review each report first)"))
        return box

    # values -----------------------------------------------------------------------------------

    def load(self, cfg: Config) -> None:
        """Show `cfg`. Fields pinned by an environment variable are locked."""
        self.cfg = cfg
        for key, w in self.fields.items():
            value = getattr(cfg, key)
            if isinstance(w, QCheckBox):
                w.setChecked(bool(value))
            elif isinstance(w, QComboBox):
                if w.findText(str(value)) < 0:
                    w.addItem(str(value))
                w.setCurrentText(str(value))
            elif isinstance(w, QSpinBox):
                w.setValue(int(value))
            elif isinstance(w, QPlainTextEdit):
                w.setPlainText(str(value))
            elif isinstance(w, HotkeyEdit):
                w.set_value(str(value))
            elif isinstance(w, QLineEdit):
                w.setText(str(value))
            w.setEnabled(True)
            w.setToolTip("")
            if cfg.sources.get(key) == "env":
                _locked(w, BY_KEY[key].env)
                if key == "log_dir":
                    self.browse_btn.setEnabled(False)
        self.key_edit.clear()
        self._show_key_status()
        self.error.hide()

    def _show_key_status(self) -> None:
        source = self.cfg.sources.get("api_key")
        if source == "env":
            self.key_status.setText(f"Using {mask(self.cfg.api_key)} from ANTHROPIC_API_KEY (environment or .env).")
        elif source == "keychain":
            self.key_status.setText(f"Saved in your keychain: {mask(self.cfg.api_key)}")
        elif self.keychain.problem:
            self.key_status.setText(f"No keychain here ({self.keychain.problem}). Use ANTHROPIC_API_KEY instead.")
        else:
            self.key_status.setText("No key yet. Get one at console.anthropic.com, then paste it here.")
        self.key_remove.setEnabled(source == "keychain")

    def values(self) -> dict[str, Any]:
        """What the form says now, typed like Config fields."""
        out: dict[str, Any] = {}
        for key, w in self.fields.items():
            if isinstance(w, QCheckBox):
                out[key] = w.isChecked()
            elif isinstance(w, QComboBox):
                out[key] = w.currentText().strip()
            elif isinstance(w, QSpinBox):
                out[key] = w.value()
            elif isinstance(w, QPlainTextEdit):
                out[key] = w.toPlainText().strip()
            elif isinstance(w, HotkeyEdit):
                out[key] = w.value
            elif isinstance(w, QLineEdit):
                out[key] = Path(w.text().strip()).expanduser() if key == "log_dir" else w.text().strip()
        return out

    def validate(self, values: dict[str, Any]) -> str | None:
        for key in ("hotkey", "voice_hotkey"):
            if values[key]:
                try:
                    parse_combo(values[key])
                except ValueError as exc:
                    return str(exc)
        if values["hotkey"] and values["hotkey"] == values["voice_hotkey"]:
            return "The two shortcuts must be different."
        if not values["model"]:
            return "Choose a model."
        if not str(values["log_dir"]).strip():
            return "Choose a folder for the journal."
        return None

    def save(self) -> bool:
        values = self.values()
        problem = self.validate(values)
        if problem:
            self.error.setText(problem)
            self.error.show()
            return False
        new_key = self.key_edit.text().strip()
        if new_key and not self.keychain.set(new_key):
            self.error.setText(f"Could not save the key to the keychain: {self.keychain.problem}")
            self.error.show()
            return False
        # Save what you changed, and keep what the file already had; never write env-pinned
        # values, or removing the variable later would leave its value stuck in the file.
        stored = self.store.load()
        changed = {
            k: v
            for k, v in values.items()
            if self.cfg.sources.get(k) != "env" and (k in stored or v != getattr(self.cfg, k))
        }
        try:
            self.store.save(changed)
        except OSError as exc:
            self.error.setText(f"Could not save settings: {exc}")
            self.error.show()
            return False
        self.close()
        self.saved.emit()
        return True

    def _remove_key(self) -> None:
        self.keychain.delete()
        self.cfg.api_key = None
        self.cfg.sources["api_key"] = "none"
        self._show_key_status()
        self.saved.emit()  # the controller drops the key it holds

    def _choose_folder(self) -> None:
        start = self.fields["log_dir"].text()
        chosen = QFileDialog.getExistingDirectory(self, "Journal folder", start)
        if chosen:
            self.fields["log_dir"].setText(chosen)

    def closeEvent(self, e) -> None:  # noqa: N802
        self.closed.emit()
        super().closeEvent(e)

    def open(self, cfg: Config) -> None:
        self.load(cfg)
        self.adjustSize()
        screen = self.screen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        bring_to_front(self)
