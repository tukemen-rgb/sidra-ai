"""The boundary is information on every row, not one row in four.

§4 + WCAG 1.4.11, C-1603. racing's draw() has said "the boundary is
information" since C-1287, and made the marks a two-tone pair so they
stand at 3:1 against road and roadside in every theme. But the marks were
only painted inside a 12-in-110 window: measured on a real frame, 19 of
80 row slots. On the other 76% the line between safe and punished was
carried by the tarmac's own contrast against the roadside - 1.012:1 on
the default theme (C-1400) - and being off the road halves the pace.

The pair now runs the whole length as a thin line, with the old ticks
kept on top of it: the line says where the road is, the ticks still say
how fast it is going by.
"""

from __future__ import annotations

import json
import re
import subprocess

from sidra_ai.creation import generate_game
from sidra_ai.creation.racing import haze_probe, probe_source


def _painted() -> dict:
    html = generate_game("レースゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=haze_probe(script),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_every_row_is_bounded_on_both_sides() -> None:
    got = _painted()
    assert got["rowSlots"] > 0
    assert got["boundedRows"] == got["rowSlots"], (
        f"only {got['boundedRows']}/{got['rowSlots']} rows carry a boundary"
    )


def test_the_ticks_rhythm_survives_under_the_line() -> None:
    """The 12-in-110 marks are speed feedback; the line must not pave them."""

    got = _painted()
    assert got["dashRows"] > 0, "the ticks are gone"
    # Still a rhythm, not a second continuous line.
    assert got["dashRows"] < got["rowSlots"] / 2, "the ticks became continuous"


def test_the_boundary_is_never_faded() -> None:
    """C-1400's haze is scenery; the thing the driver reads stays opaque."""

    got = _painted()
    assert got["edgeAlphas"] == [1]


def test_the_two_tone_contract_is_untouched() -> None:
    """C-1603 changed where the pair is painted, not what it is made of."""

    html = generate_game("レースゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=probe_source(script),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert run.returncode == 0, run.stderr[:400]
    edge = json.loads(run.stdout.strip().splitlines()[-1])["edge"]
    assert edge["a"] != edge["b"], "the pair collapsed to one tone"
    assert len(edge["scenes"]) == 3
