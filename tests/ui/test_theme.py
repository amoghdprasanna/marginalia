"""The colour tokens: readable on every surface, and told apart without full colour vision."""

import itertools
import re
from pathlib import Path

import pytest

from marginalia.ui import theme

WHITE = (255, 255, 255)


def rgb(hex_: str) -> tuple[int, int, int]:
    h = hex_.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def over(alpha: int, base: tuple[int, int, int]) -> tuple[int, ...]:
    """White at `alpha` laid over `base`, as a style sheet's rgba() fill is drawn."""
    return tuple(round(w * alpha / 255 + b * (1 - alpha / 255)) for w, b in zip(WHITE, base, strict=True))


def linear(v: int) -> float:
    v /= 255
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(c) -> float:
    r, g, b = (linear(v) for v in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


SLATE = rgb(theme.SLATE_HEX)
SURFACES = {
    "slate": SLATE,
    "sidebar": rgb(theme.SIDEBAR_HEX),
    "raised": rgb(theme.RAISED_HEX),
    "card": over(theme.FILL_CARD, SLATE),
    "field": over(theme.FILL_FIELD, SLATE),
    "button": over(theme.FILL_BUTTON, SLATE),
    "hovered button": over(theme.FILL_BUTTON_HOVER, SLATE),
}
# Which text colour is drawn on which surface. Status colours never sit on a button.
PLAIN = ("slate", "sidebar", "raised", "card", "field")
TEXT_ON = {
    "TEXT_HEX": list(SURFACES),
    "TEXT_SOFT_HEX": list(SURFACES),
    "MUTED_HEX": list(SURFACES),
    "AMBER_HEX": list(SURFACES),
    "OK_HEX": PLAIN,
    "ERROR_HEX": PLAIN,
}


@pytest.mark.parametrize(("token", "surface"), [(t, s) for t, on in TEXT_ON.items() for s in on])
def test_text_is_readable_where_it_is_drawn(token, surface):
    """WCAG 2.1 1.4.3: 4.5:1 for text."""
    assert contrast(rgb(getattr(theme, token)), SURFACES[surface]) >= 4.5


def test_dark_text_on_the_amber_button_in_every_state():
    for fill in (theme.AMBER_HEX, theme.AMBER_HOVER_HEX, theme.AMBER_DOWN_HEX):
        assert contrast(SLATE, rgb(fill)) >= 4.5


def test_you_can_see_where_to_type():
    """WCAG 2.1 1.4.11: a field's edge, which is what tells you it's a field, at 3:1."""
    edge = rgb(theme.FIELD_EDGE_HEX)
    assert contrast(edge, SLATE) >= 3 and contrast(edge, SURFACES["field"]) >= 3


# Colour blindness: Machado et al. (2009), severity 1, applied in linear RGB.
CVD = {
    "protanopia": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "deuteranopia": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
    "tritanopia": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]],
}


def lab(lin):
    r, g, b = lin
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.9505
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.089

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def seen(hex_: str, matrix) -> tuple[float, ...]:
    lin = [linear(v) for v in rgb(hex_)]
    return lab([max(0.0, min(1.0, sum(matrix[i][j] * lin[j] for j in range(3)))) for i in range(3)])


@pytest.mark.parametrize("vision", CVD)
def test_ready_needs_you_and_failed_stay_apart_for_colour_blind_eyes(vision):
    """The setup check and the bubble also use shapes; the colours shouldn't fight them. Before this
    palette, 'ready' green and 'error' coral were 9.6 apart (CIE76) to deuteranopes."""
    states = [theme.OK_HEX, theme.AMBER_HEX, theme.ERROR_HEX, theme.MUTED_HEX]
    for a, b in itertools.combinations(states, 2):
        da, db = seen(a, CVD[vision]), seen(b, CVD[vision])
        assert sum((x - y) ** 2 for x, y in zip(da, db, strict=True)) ** 0.5 >= 20, f"{a} and {b}"


def test_colours_live_in_the_theme():
    """One place to change a colour: the UI's other modules use the tokens, not literals."""
    literal = re.compile(r"#[0-9A-Fa-f]{6}\b(?<!#FFFFFF)|rgba\(|QColor\(\d")
    ui = Path(theme.__file__).parent
    found = [
        f"{path.name}:{n}"
        for path in ui.glob("*.py")
        if path.name != "theme.py"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if literal.search(line)
    ]
    assert not found
