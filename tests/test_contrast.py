"""WCAG 2.2 AA contrast, computed from the shipped CSS.

This exists because the original audit checked TOKEN pairs (ink on the three
backgrounds) and never checked FILLED pairs — text on a filled accent. That
gap shipped `.btn.accent` at 2.81:1 in light mode, found by a human looking at
a sibling design rather than by any test here.

So this parses the real stylesheet and checks every rule that sets both a
background and a colour, in both themes. An audit that only checks what you
remembered to list is not an audit.
"""
import re
from pathlib import Path

import pytest

CONSOLE = Path(__file__).resolve().parents[1] / "api" / "static" / "index.html"
CSS = CONSOLE.read_text(encoding="utf-8")

AA_TEXT = 4.5
AA_NON_TEXT = 3.0


def _lum(h: str) -> float:
    h = h.lstrip("#")
    ch = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(c) for c in ch)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    l1, l2 = sorted((_lum(a), _lum(b)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def _tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", block))


LIGHT = _tokens(re.search(r":root\{(.*?)\}", CSS, re.S).group(1))
DARK = dict(LIGHT)
DARK.update(_tokens(re.search(r':root\[data-theme="dark"\]\{(.*?)\}', CSS, re.S).group(1)))

THEMES = (("light", LIGHT), ("dark", DARK))


def _filled_pairs():
    """Every rule setting BOTH a background and a colour from tokens."""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^}]*)\}", CSS):
        sel = m.group(1).strip().splitlines()[-1].strip()
        body = m.group(2)
        bg = re.search(r"background(?:-color)?:\s*var\(--([a-z0-9-]+)\)", body)
        fg = re.search(r"(?<!-)color:\s*var\(--([a-z0-9-]+)\)", body)
        if bg and fg and bg.group(1) in LIGHT and fg.group(1) in LIGHT:
            out.append((sel, fg.group(1), bg.group(1)))
    return out


@pytest.mark.parametrize("theme,palette", THEMES)
def test_body_text_tokens_pass_on_every_ground(theme, palette):
    grounds = ("bg", "surface", "surface-2")
    for fg in ("ink", "ink-2", "ink-3", "accent", "good", "danger"):
        worst = min(contrast(palette[fg], palette[g]) for g in grounds)
        assert worst >= AA_TEXT, f"{theme}: --{fg} worst {worst:.2f} < {AA_TEXT}"


@pytest.mark.parametrize("theme,palette", THEMES)
def test_ui_component_colour_passes(theme, palette):
    worst = min(contrast(palette["line-strong"], palette[g]) for g in ("bg", "surface", "surface-2"))
    assert worst >= AA_NON_TEXT, f"{theme}: --line-strong {worst:.2f} < {AA_NON_TEXT}"


@pytest.mark.parametrize("theme,palette", THEMES)
def test_every_filled_pair_passes(theme, palette):
    """The check that would have caught .btn.accent at 2.81:1."""
    failures = [
        (sel, fg, bg, contrast(palette[fg], palette[bg]))
        for sel, fg, bg in _filled_pairs()
        if contrast(palette[fg], palette[bg]) < AA_TEXT
    ]
    assert not failures, f"{theme}: " + "; ".join(
        f"{s} ({f} on {b}) = {r:.2f}" for s, f, b, r in failures
    )


def test_the_sweep_actually_finds_pairs():
    """A sweep that matches nothing would pass vacuously forever."""
    assert len(_filled_pairs()) >= 10
