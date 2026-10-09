"""The Settings window: everything that used to need a .env file, plus the API key in the keychain.

It edits a copy of the values and writes the settings file only on Save; the controller then
reloads the config and applies what changed (ADR 0015). Fields an environment variable pins
are shown but locked, with the variable's name, so an edit is never silently ignored.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
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
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import BY_KEY, LOG_LEVELS, WHISPER_MODELS, Config, SettingsStore
from ..hotkeys import Combo, format_combo, parse_combo, to_text
from ..secrets import Keychain, mask
from .theme import DIALOG_STYLE, bring_to_front

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


CLI_FLAGS = {"hotkey_enabled": "--no-hotkey", "ocr_enabled": "--no-ocr", "voice_enabled": "--no-voice"}


def _locked(widget: QWidget, why: str) -> None:
    widget.setEnabled(False)
    widget.setToolTip(why)


# Names people recognise, and what each choice trades (docs/design.md: speak the user's language).
MODEL_CHOICES = (
    ("claude-opus-5-5", "Claude Opus 5.5", "Best answers. The default."),
    ("claude-sonnet-5-5", "Claude Sonnet 5.5", "Faster, about half the price."),
    ("claude-haiku-5-5", "Claude Haiku 5.5", "Fastest and cheapest; fine for quick definitions."),
    ("claude-fable-5-1", "Claude Fable 5.1", "Most capable; slower and pricier."),
)
EFFORT_CHOICES = (
    ("low", "Quick", "Answers sooner; thinks less."),
    ("medium", "Balanced", "The default."),
    ("high", "Thorough", "Thinks harder; good for derivations."),
    ("xhigh", "Very thorough", "Slower still."),
    ("max", "Maximum", "As deep as it goes; slowest and priciest."),
)
LOG_CHOICES = tuple((v, v.capitalize(), "") for v in LOG_LEVELS)
LABEL_WIDTH = 118  # one label column for every group, so the fields line up down the window


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
        self._loading = False
        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.hide()

        self.advanced = self._advanced_group()
        self.advanced.hide()
        self.advanced_toggle = QPushButton("Show advanced settings")
        self.advanced_toggle.setObjectName("link")
        self.advanced_toggle.setCursor(Qt.PointingHandCursor)
        self.advanced_toggle.clicked.connect(self._toggle_advanced)

        content = QWidget()
        inner = QVBoxLayout(content)
        inner.setContentsMargins(18, 16, 18, 4)
        inner.setSpacing(12)
        inner.addWidget(self._claude_group())
        inner.addWidget(self._keys_group())
        inner.addWidget(self._voice_group())
        inner.addWidget(self._journal_group())
        inner.addWidget(self.advanced_toggle, 0, Qt.AlignLeft)
        inner.addWidget(self.advanced)
        inner.addStretch(1)
        # Scrolls on a small screen; the buttons stay put below it, always reachable.
        self.scroll = QScrollArea()
        self.scroll.setWidget(content)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._content = content
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 16)
        lay.setSpacing(10)
        lay.addWidget(self.scroll, 1)
        self.error.setContentsMargins(18, 0, 18, 0)
        lay.addWidget(self.error)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(18, 0, 18, 0)
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
        self.setMinimumWidth(600)
        self.load(cfg)

    # building ---------------------------------------------------------------------------------

    def _form(self, title: str) -> tuple[QGroupBox, QFormLayout]:
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        return box, form

    def _row(self, form: QFormLayout, label: str, field, help_text: str = "") -> None:
        """A labelled row, with a line of help under the field when the label alone isn't enough."""
        lab = QLabel(label)
        lab.setMinimumWidth(LABEL_WIDTH)  # a column that lines up, but grows rather than clip a larger font
        lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if not help_text:
            form.addRow(lab, field)
            return
        holder = QWidget()
        col = QVBoxLayout(holder)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(3)
        col.addLayout(field) if isinstance(field, QHBoxLayout) else col.addWidget(field)
        hint = QLabel(help_text)
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        col.addWidget(hint)
        form.addRow(lab, holder)
        lab.setAlignment(Qt.AlignRight | Qt.AlignTop)
        lab.setContentsMargins(0, 6, 0, 0)

    def _choice(self, key: str, choices) -> QComboBox:
        """A drop-down showing friendly names; the stored value is the item's data."""
        w = QComboBox()
        # Size to the column, not to the longest description (which would widen the whole window).
        w.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        w.setMinimumContentsLength(16)
        for value, name, note in choices:
            w.addItem(f"{name}  ·  {note}" if note else name, value)
        w.currentIndexChanged.connect(self._changed)
        self.fields[key] = w
        return w

    def _check(self, key: str, text: str) -> QCheckBox:
        w = QCheckBox(text)
        w.toggled.connect(self._changed)
        self.fields[key] = w
        return w

    def _claude_group(self) -> QGroupBox:
        box, form = self._form("Claude")
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Paste a key that starts with sk-ant-")
        self.key_edit.textChanged.connect(self._changed)
        self.key_status = QLabel()
        self.key_status.setObjectName("muted")
        self.key_status.setWordWrap(True)
        self.key_status.setOpenExternalLinks(True)
        self.key_remove = QPushButton("Remove")
        self.key_remove.clicked.connect(self._remove_key)
        row = QHBoxLayout()
        row.addWidget(self.key_edit, 1)
        row.addWidget(self.key_remove)
        holder = QWidget()
        col = QVBoxLayout(holder)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(3)
        col.addLayout(row)
        col.addWidget(self.key_status)
        self._row(form, "API key", holder)
        self._row(form, "Model", self._choice("model", MODEL_CHOICES))
        self._row(form, "Thinking", self._choice("effort", EFFORT_CHOICES), "How long Claude thinks before it answers.")
        context = QPlainTextEdit()
        context.setFixedHeight(76)
        context.textChanged.connect(self._changed)
        self.fields["user_context"] = context
        self._row(form, "About you", context, "Claude pitches its answers at this. Your field, your level.")
        return box

    def _keys_group(self) -> QGroupBox:
        box, form = self._form("Shortcuts")
        self._row(form, "", self._check("hotkey_enabled", "Shortcuts work in any app"))
        ask, voice = HotkeyEdit(), HotkeyEdit()
        ask.changed.connect(self._changed)
        voice.changed.connect(self._changed)
        self.fields["hotkey"], self.fields["voice_hotkey"] = ask, voice
        self._row(form, "Ask by typing", ask)
        self._row(form, "Hold to talk", voice, "Click a box, then press the keys. Backspace clears it.")
        return box

    def _voice_group(self) -> QGroupBox:
        box, form = self._form("Voice and reading")
        self._row(form, "", self._check("voice_enabled", "Ask by voice"), "Speech is transcribed on this computer.")
        speech = QComboBox()
        speech.setEditable(True)
        speech.addItems(WHISPER_MODELS)
        speech.currentTextChanged.connect(self._changed)
        self.fields["whisper_model"] = speech
        self._row(form, "Speech model", speech, "tiny.en is fastest; small.en understands more. Downloaded once.")
        self._row(form, "", self._check("ocr_enabled", "Read text on screen"), "Sharper pointing at small print.")
        return box

    def _journal_group(self) -> QGroupBox:
        box, form = self._form("Journal and updates")
        folder = QLineEdit()
        folder.textChanged.connect(self._changed)
        self.fields["log_dir"] = folder
        browse = QPushButton("Choose…")
        browse.clicked.connect(self._choose_folder)
        self.browse_btn = browse
        row = QHBoxLayout()
        row.addWidget(folder, 1)
        row.addWidget(browse)
        self._row(form, "Folder", row, "Every question, answer and screenshot is saved here.")
        self._row(form, "", self._check("check_updates", "Check for new versions"))
        crash = self._check("crash_reports", "Offer to report crashes")
        self._row(form, "", crash, "You see each report before anything is sent.")
        return box

    def _advanced_group(self) -> QGroupBox:
        box, form = self._form("Advanced")
        tokens = QSpinBox()
        tokens.setRange(1024, 128000)
        tokens.setSingleStep(1000)
        tokens.valueChanged.connect(self._changed)
        self.fields["max_tokens"] = tokens
        self._row(form, "Max tokens", tokens, "Room for thinking plus the answer. Raise it if answers get cut off.")
        self._row(form, "", self._check("hires", "High-resolution images"), "Only for models that accept them.")
        self._row(form, "Console detail", self._choice("log_level", LOG_CHOICES))
        self._row(form, "", self._check("save_cases", "Save questions as eval cases"))
        return box

    def _toggle_advanced(self) -> None:
        show = not self.advanced.isVisible()
        self.advanced.setVisible(show)
        self.advanced_toggle.setText("Hide advanced settings" if show else "Show advanced settings")
        self._fit_to_screen()
        if show:
            QTimer.singleShot(0, self, lambda: self.scroll.ensureWidgetVisible(self.advanced))

    def _fit_to_screen(self) -> None:
        """As tall as the content but never taller than the screen; wide enough that nothing is cut
        off, whatever the platform's fonts (Windows' run larger than macOS')."""
        self._content.adjustSize()
        bar = self.scroll.verticalScrollBar().sizeHint().width()
        wide = max(600, self._content.minimumSizeHint().width() + bar + 2 * self.scroll.frameWidth() + 4)
        room = self.screen().availableGeometry()
        want = self._content.sizeHint().height() + 70  # the buttons row and margins
        self.resize(min(wide, room.width() - 40), min(want, room.height() - 40))

    # values -----------------------------------------------------------------------------------

    def set_value(self, key: str, value) -> None:
        w = self.fields[key]
        if isinstance(w, QCheckBox):
            w.setChecked(bool(value))
        elif isinstance(w, QComboBox) and not w.isEditable():
            i = w.findData(value)
            if i < 0:  # a value set outside the window (an env var, an older version): keep it visible
                w.addItem(str(value), value)
                i = w.count() - 1
            w.setCurrentIndex(i)
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

    def load(self, cfg: Config) -> None:
        """Show `cfg`. Fields pinned by an environment variable or a switch are locked."""
        self.cfg = cfg
        self._loading = True
        self.browse_btn.setEnabled(True)
        for key, w in self.fields.items():
            self.set_value(key, getattr(cfg, key))
            w.setEnabled(True)
            w.setToolTip("")
            source = cfg.sources.get(key)
            if source == "env":
                env = BY_KEY[key].env
                _locked(w, f"Set by {env} in your environment or .env file; remove it there to edit here.")
            elif source == "command line":
                _locked(w, f"Set by {CLI_FLAGS.get(key, 'a command-line switch')} for this run.")
            if key == "log_dir" and not w.isEnabled():
                self.browse_btn.setEnabled(False)
        self.key_edit.clear()
        self._loading = False
        self._show_key_status()
        self.error.hide()
        self._changed()

    def _show_key_status(self) -> None:
        source = self.cfg.sources.get("api_key")
        if source == "env":
            self.key_status.setText(f"Using {mask(self.cfg.api_key)} from ANTHROPIC_API_KEY (environment or .env).")
        elif source == "keychain":
            self.key_status.setText(f"Saved in your keychain: {mask(self.cfg.api_key)}")
        elif self.keychain.problem:
            self.key_status.setText(f"No keychain here ({self.keychain.problem}). Use ANTHROPIC_API_KEY instead.")
        else:
            self.key_status.setText(
                'No key yet. Create one at <a href="https://console.anthropic.com/settings/keys" '
                'style="color:#FFB224">console.anthropic.com</a>, then paste it here.'
            )
        self.key_remove.setEnabled(source == "keychain")

    def values(self) -> dict[str, Any]:
        """What the form says now, typed like Config fields."""
        out: dict[str, Any] = {}
        for key, w in self.fields.items():
            if isinstance(w, QCheckBox):
                out[key] = w.isChecked()
            elif isinstance(w, QComboBox) and not w.isEditable():
                out[key] = w.currentData()
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

    def dirty(self) -> bool:
        """Is there anything to save?"""
        if self.key_edit.text().strip():
            return True
        return any(v != getattr(self.cfg, k) for k, v in self.values().items())

    def _changed(self, *_args) -> None:
        if not self._loading:
            self.save_btn.setEnabled(self.dirty())  # a Save that does nothing teaches you to distrust it

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
        # Save what you changed, and keep what the file already had. Never write a value an
        # environment variable or a command-line switch decided: it would outlive that override.
        stored = self.store.load()
        changed = {
            k: v
            for k, v in values.items()
            if self.cfg.sources.get(k) not in ("env", "command line") and (k in stored or v != getattr(self.cfg, k))
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

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e) -> None:  # noqa: N802
        self.closed.emit()
        super().closeEvent(e)

    def open(self, cfg: Config) -> None:
        self.load(cfg)
        self._fit_to_screen()
        screen = self.screen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        bring_to_front(self)
