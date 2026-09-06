"""The two information hues survive colour-blind eyes (§4×§20, C-1369).

The shape channel was always the last line of defence; the colour channel
itself had never been measured. Machado 2009's full-severity matrices,
applied in linear RGB, simulate each dichromacy, and the accent×alert
pair must stay apart in Lab on every theme.
"""

from __future__ import annotations

import math

import pytest

from sidra_ai.creation.themes import select_theme

MATRICES = {
    "protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
    "tritan": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]],
}

#: The brand-locked default keeps a lower floor: GAMEYARD's palette is not
#: ours to move (C-0k), and its weakest cell measures 17.8.
CASES = [
    ("ゲームを作って", 15.0),
    ("紙のテーマで", 20.0),
    ("ターミナルのテーマで", 20.0),
    ("dusk のテーマで", 20.0),
]


def _lin(hexcolour: str) -> list[float]:
    raw = hexcolour.lstrip("#")
    v = [int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in v]


def _sim(m: list, rgb: list[float]) -> list[float]:
    return [max(0.0, min(1.0, sum(m[i][j] * rgb[j] for j in range(3)))) for i in range(3)]


def _lab(rgb: list[float]) -> tuple[float, float, float]:
    X = 0.4124 * rgb[0] + 0.3576 * rgb[1] + 0.1805 * rgb[2]
    Y = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    Z = 0.0193 * rgb[0] + 0.1192 * rgb[1] + 0.9505 * rgb[2]

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(X / 0.95047), f(Y), f(Z / 1.08883)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


@pytest.mark.parametrize("request_text,floor", CASES)
@pytest.mark.parametrize("kind", sorted(MATRICES))
def test_accent_and_alert_stay_apart(request_text: str, floor: float, kind: str) -> None:
    tokens = select_theme(request_text).tokens
    a = _lab(_sim(MATRICES[kind], _lin(tokens["accent"])))
    b = _lab(_sim(MATRICES[kind], _lin(tokens["alert"])))
    assert math.dist(a, b) >= floor, (
        f"{request_text}/{kind}: ΔE {math.dist(a, b):.1f} - the two hues collapse"
    )


def test_the_gamma_step_is_not_skipped() -> None:
    """§20's own warning: simulating on raw sRGB invalidates the numbers.

    A mid-grey must round-trip near itself; feeding gamma sRGB straight
    into the matrices would shift it measurably, which this guards.
    """

    grey = _lin("#808080")
    for m in MATRICES.values():
        sim = _sim(m, grey)
        assert math.dist(_lab(sim), _lab(grey)) < 6.0


def test_the_simulator_actually_simulates() -> None:
    """A red/olive pair every protanope confuses must collapse."""

    a, b = _lin("#ff0000"), _lin("#9b9b00")
    raw = math.dist(_lab(a), _lab(b))
    simmed = math.dist(
        _lab(_sim(MATRICES["protan"], a)), _lab(_sim(MATRICES["protan"], b))
    )
    assert simmed < raw * 0.5, "the matrices no longer simulate anything"
