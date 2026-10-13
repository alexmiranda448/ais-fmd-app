"""
Guards for the Pebble theme.

`st.dataframe` paints a canvas grid from Streamlit's own theme, which never
sees the app stylesheet, so `.streamlit/config.toml` has to agree with the
tokens in `ais_fmd/ui/theme.py` or tables and widgets drift from the page.

Pebble replaced the light/dark pair with one light palette, so the old guards
for the mode switch's localStorage key went with the switch.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from ais_fmd.ui import theme

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    tomllib = pytest.importorskip("tomli")

CONFIG = Path(__file__).resolve().parent.parent / ".streamlit" / "config.toml"


def test_config_matches_tokens():
    """Streamlit's own chrome must agree with the app's tokens."""
    section = tomllib.loads(CONFIG.read_text(encoding="utf-8"))["theme"]
    assert section["base"] == "light"
    pairs = {
        "backgroundColor": theme.CANVAS,
        "secondaryBackgroundColor": theme.SUBTLE,
        "textColor": theme.INK,
        "primaryColor": theme.ACCENT,
        "borderColor": theme.GRID,
    }
    for key, expected in pairs.items():
        assert section[key].upper() == expected.upper(), (
            f"[theme] {key} is {section[key]} but theme.py says {expected}."
        )


def _contrast(foreground: str, background: str) -> float:
    def channel(value: float) -> float:
        value /= 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    def luminance(colour: str) -> float:
        colour = colour.lstrip("#")
        r, g, b = (int(colour[i : i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

    a, b = luminance(foreground), luminance(background)
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize(
    "foreground, background",
    [
        (theme.INK, theme.CANVAS),
        (theme.INK, theme.CARD),
        (theme.INK, theme.SUBTLE),
        (theme.INK_SOFT, theme.CANVAS),
        (theme.INK_SOFT, theme.CARD),
        (theme.INK_SOFT, theme.SUBTLE),
        (theme.ACCENT_DIM, theme.ACCENT_TINT),  # "over" pill
        (theme.ACCENT_DIM, theme.CARD),         # hero delta pill
        ("#FFFFFF", theme.ACCENT),              # hero card text
        (theme.ACCENT, theme.CARD),
    ],
)
def test_text_clears_aa(foreground: str, background: str):
    """
    Body text and pills must clear 4.5:1.

    KNOWN SHORT, left as designed pending sign-off: INK_MUTE axis ticks on a
    card (3.6:1) and the green on-track pill (POSITIVE on POSITIVE_TINT, 4.4:1).
    """
    ratio = _contrast(foreground, background)
    assert ratio >= 4.5, f"{foreground} on {background} is {ratio:.2f}:1"


def test_active_returns_the_one_palette():
    """Pages the redesign did not touch still read colours via active()."""
    palette = theme.active()
    assert palette is theme.PEBBLE
    assert palette.income == theme.INCOME and palette.over == theme.OVER


def test_css_carries_no_unresolved_tokens():
    css = theme.app_css()
    assert not re.findall(r"\{[A-Z_]+\}", css), "unrendered f-string token in the stylesheet"
    assert "prefers-reduced-motion" in css


def test_template_grounds_are_transparent():
    template = theme.build_template()
    assert template.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert template.layout.plot_bgcolor == "rgba(0,0,0,0)"
