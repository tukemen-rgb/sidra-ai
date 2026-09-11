"""The pad is thumb-sized where a thumb lands (§4, C-1666).

§4 records a 48dp minimum with 8dp spacing, and C-1019 built the canvas
pad that is the only way to play any of this on a phone. Neither number
was ever measured against a button. ``evals/touch_targets.py`` regexes the
generated HTML for a ``min-height`` inside a ``pointer:coarse`` block and
never starts node - its own docstring says the end-to-end proof "ran at
fix" - and the pad's own contracts check that it is painted
(``creation_pad_painted``) and that it can be seen
(``creation_pad_visible``), never how big it is.

Measured, the R and P buttons were ``b*0.7`` = 39.2 CSS px tall, 18% under
the floor. The eighth instance of a ledger checked where the canvas should
have been (C-1615 onward), on the number closest to a finger.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.touchpad import padsize_probe

#: One scale where canvas and CSS pixels agree, and one modest zoom - the
#: direction in which a thumb-sized control shrinks. Not 2x: this probe
#: holds the canvas height fixed while shrinking the CSS width, so a large
#: ratio describes a canvas whose CSS aspect does not match its pixel
#: aspect, and the pad overflows the top edge. That reading would be about
#: the staging, not the product.
SHAPES = ((720, 720), (720, 540))


def _measured(canvas_w: int, css_w: int) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("キャッチゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=padsize_probe(script.group(1), canvas_w=canvas_w, css_w=css_w),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(("canvas_w", "css_w"), SHAPES)
def test_every_button_clears_the_48dp_floor(canvas_w, css_w) -> None:
    seen = _measured(canvas_w, css_w)

    assert seen["count"], "the pad drew no buttons at all"
    assert seen["allDrawn"], "a button was laid out but never painted"
    assert seen["allOnCanvas"], "a button is laid out off the canvas"
    assert seen["smallest"] >= 48, [
        (p["id"], round(p["w"], 1), round(p["h"], 1)) for p in seen["plates"]
    ]


@pytest.mark.parametrize(("canvas_w", "css_w"), SHAPES)
def test_the_buttons_are_spaced_and_never_overlap(canvas_w, css_w) -> None:
    """A spacing rule that does not also forbid overlap is not a spacing
    rule - two buttons on top of each other are 0 apart by every measure
    except the one that matters."""

    seen = _measured(canvas_w, css_w)

    assert seen["overlaps"] == 0, seen["plates"]
    assert seen["minGap"] >= 8, seen["minGap"]


def test_shrinking_the_glass_does_not_shrink_the_thumb() -> None:
    """The layout is in canvas pixels and the rule is in CSS pixels, so a
    zoomed page is where the floor would quietly be breached."""

    wide = _measured(720, 720)
    narrow = _measured(720, 540)

    assert narrow["scale"] > wide["scale"], (wide["scale"], narrow["scale"])
    assert narrow["smallest"] == pytest.approx(wide["smallest"]), (
        wide["smallest"], narrow["smallest"]
    )


def test_the_pause_button_stays_clear_of_the_countdown() -> None:
    """Raising P to a thumb's height pushed its top to y=67, seven pixels
    inside the band the countdown owns (C-1417), and no gap honouring the
    8dp rule brought it back. It sits beside R now instead of above it."""

    seen = _measured(720, 720)
    by_id = {p["id"]: p for p in seen["plates"]}
    if "p" in by_id:
        assert by_id["p"]["y"] >= 44 + 30, by_id["p"]


def test_the_round_controls_are_the_ones_that_were_short() -> None:
    """Named so the regression has a face: R and P were 39.2 and the
    arrows were always 56."""

    seen = _measured(720, 720)
    by_id = {p["id"]: p for p in seen["plates"]}

    for flat in ("r", "p"):
        if flat in by_id:
            assert by_id[flat]["h"] >= 48, by_id[flat]
