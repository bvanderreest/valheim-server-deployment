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


# ── Chart series colours ──────────────────────────────────────────────────────
# The console's data-viz palette is NOT covered by the token tests above: the
# series hues live on `.perf`, not on `:root`, precisely so they cannot be
# mistaken for UI tokens. They still have to clear the same gates, plus one the
# UI tokens do not have — two marks distinguished ONLY by hue must stay apart
# under colour-vision deficiency. Nothing about "these two look different to me"
# is evidence; it is computed here so a future colour change fails CI instead of
# failing a colourblind player.

def _series_tokens(scope: str) -> dict[str, str]:
    m = re.search(re.escape(scope) + r"\{(--s-[^}]*)\}", CSS)
    assert m, f"no series palette found for scope {scope}"
    return dict(re.findall(r"--(s-[a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", m.group(1)))


SERIES = (
    ("light", _series_tokens(".perf"), LIGHT["surface"]),
    ("dark", _series_tokens(':root[data-theme="dark"] .perf'), DARK["surface"]),
)


def _lin(h: str) -> list[float]:
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def _oklab(h: str) -> tuple[float, float, float]:
    r, g, b = _lin(h)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


# Machado, Oliveira & Fernandes (2009), severity 1.0, on linear RGB.
_MACHADO = {
    "protan": [[0.152286, 1.052583, -0.204868],
               [0.114503, 0.786281, 0.099216],
               [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968],
               [0.280085, 0.672501, 0.047413],
               [-0.011820, 0.042940, 0.968881]],
}


def _simulate(h: str, kind: str) -> str:
    v = _lin(h)
    out = []
    for row in _MACHADO[kind]:
        c = max(0.0, min(1.0, sum(row[i] * v[i] for i in range(3))))
        c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        out.append(round(max(0.0, min(1.0, c)) * 255))
    return "#%02x%02x%02x" % tuple(out)


def _dE(a: str, b: str) -> float:
    pa, pb = _oklab(a), _oklab(b)
    return 100 * sum((pa[i] - pb[i]) ** 2 for i in range(3)) ** 0.5


@pytest.mark.parametrize("mode,series,surface", SERIES)
def test_series_marks_are_visible_against_the_chart_surface(mode, series, surface):
    """A mark is a non-text UI component: 3:1 or it disappears on the card."""
    assert series, f"{mode}: no series colours parsed"
    for name, hex_ in series.items():
        c = contrast(hex_, surface)
        assert c >= AA_NON_TEXT, f"{mode}: --{name} {hex_} is {c:.2f}:1 on {surface}, needs {AA_NON_TEXT}"


@pytest.mark.parametrize("mode,series,surface", SERIES)
def test_series_stay_distinct_under_colour_blindness(mode, series, surface):
    """Save stall and GC pause are told apart by hue on the chart. Under protan
    or deutan vision that hue difference has to survive — OKLab ΔE×100 >= 8 is
    the skill's target and the legend/table are not a substitute for it here,
    because the CHART is where the two are compared."""
    hexes = list(series.values())
    for i in range(len(hexes)):
        for j in range(i + 1, len(hexes)):
            worst = min(_dE(_simulate(hexes[i], k), _simulate(hexes[j], k))
                        for k in _MACHADO)
            assert worst >= 8.0, (
                f"{mode}: {hexes[i]} vs {hexes[j]} collapse to ΔE {worst:.1f} "
                f"under CVD (need >= 8). Re-step them, do not ship them.")


@pytest.mark.parametrize("mode,series,surface", SERIES)
def test_series_are_distinct_to_full_colour_vision_too(mode, series, surface):
    hexes = list(series.values())
    for i in range(len(hexes)):
        for j in range(i + 1, len(hexes)):
            d = _dE(hexes[i], hexes[j])
            assert d >= 15.0, f"{mode}: {hexes[i]} vs {hexes[j]} ΔE {d:.1f} < 15"
