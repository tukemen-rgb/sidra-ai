"""The colour well had no range, and it is the control that decides reading.

§4 × §9 学び (4), C-1737. The tuning panel is this product's answer to
"a non-engineer can edit it" (C-1113), and every control in it is bounded
by what the page can survive: ``tuneNum`` rounds a number into the
author's own range, ``tuneChoice`` drops a value that is not on the list.
``tuneText`` checked one thing about a colour - that it is six hex digits
- and let all 16.7 million through.

The product already owns this floor. ``themes.CONTRAST_FLOORS`` carries
``("accent", "surface", 3.0)`` and a *theme* that fails it is dropped from
the catalogue. So the rule was enforced where the product picks the colour
and not measured at all where the operator picks it - one more contract
that only looks at one side of its own rule.

Measured on the real page before the fix: the shipped accent stands at
13.30:1 against the ground and ``#0b0f17`` from the colour well at
1.05:1, with no rounding and nothing said. What that colour paints is not
decoration - it is the HUD's headings, the briefing's three labels, the
combo readout and the pad's restart bar.

Both directions. A page that always paints its own accent passes the
first check on its own, and that implementation is "the colour well does
nothing" - the defect C-1729 spent a cycle removing.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.themes import ACCENT_FLOOR, CONTRAST_FLOORS, contrast_ratio
from sidra_ai.creation.tuning import SPEED_BINDING, probe_source

TEMPLATE = "adventure"
#: Under the floor on this product's dark ground, and over it.
UNDER = ("#0b0f17", "#001a00", "#1a0000", "#000000", "#404040")
OVER = ("#2ee6ff", "#ff00aa", "#ffffff")


def _script(template: str = TEMPLATE) -> str:
    page = generate_game("ゲームを作って", template=template).html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None
    return found.group(1)


def _run(script: str, accent: str | None, template: str = TEMPLATE) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to build the panel")
    source = probe_source(
        script,
        stored=({f"sidra.tune.{template}": {"accent": accent}} if accent else {}),
        speed_expr=SPEED_BINDING[template],
    )
    probe = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=180
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def ground() -> str:
    seen = _run(_script(), None)
    assert seen["accentGround"], "the page does not say what its accent sits on"
    return seen["accentGround"]


def test_the_floor_is_the_one_the_themes_are_held_to() -> None:
    """Not a new number: the line that drops a theme from the catalogue."""

    assert ("accent", "surface", ACCENT_FLOOR) in CONTRAST_FLOORS
    assert _run(_script(), None)["accentFloor"] == ACCENT_FLOOR


def test_the_chosen_colours_are_actually_under_and_over(ground: str) -> None:
    """Or the two halves below would be testing nothing."""

    for colour in UNDER:
        assert contrast_ratio(colour, ground) < ACCENT_FLOOR, colour
    for colour in OVER:
        assert contrast_ratio(colour, ground) >= ACCENT_FLOOR, colour


@pytest.mark.parametrize("colour", UNDER)
def test_a_colour_under_the_floor_is_lifted_to_it(colour: str, ground: str) -> None:
    seen = _run(_script(), colour)
    painted = seen["accentSeen"]
    assert contrast_ratio(painted, ground) >= ACCENT_FLOOR, (colour, painted)


@pytest.mark.parametrize("colour", UNDER)
def test_the_hue_is_the_operators_and_only_the_brightness_moves(
    colour: str, ground: str
) -> None:
    """Scaled, not mixed.

    Mixing toward white was the first answer and the measurement rejected
    it: ``#0b0f17`` came back ``#5d6065``, a grey nobody chose. Scaling
    the three channels by one factor keeps their ratios, which is the hue.
    """

    was = [int(colour[i : i + 2], 16) for i in (1, 3, 5)]
    if max(was) == 0:  # black has no hue to keep
        return
    now = [int(_run(_script(), colour)["accentSeen"][i : i + 2], 16) for i in (1, 3, 5)]
    assert was.index(max(was)) == now.index(max(now)), (was, now)
    # ...and the colour keeps its chroma, which the dominant channel
    # alone cannot see: mixing #0b0f17 toward white left blue on top
    # (93, 96, 101) while the colour itself became a grey. Scaling all
    # three channels by one factor leaves (max-min)/max exactly where it
    # was; mixing drives it to zero.
    chroma = lambda rgb: (max(rgb) - min(rgb)) / max(max(rgb), 1)
    assert chroma(now) == pytest.approx(chroma(was), abs=0.1), (was, now)


@pytest.mark.parametrize("colour", UNDER)
def test_the_panel_says_it_disagreed(colour: str) -> None:
    """In words on the page, not a flag in the facts (C-1722)."""

    seen = _run(_script(), colour)
    note = seen["accentNote"]
    assert note, "色を動かしておいて何も言わない"
    assert seen["accentSeen"] in note, note
    assert f"{ACCENT_FLOOR:.1f}" in note, note
    assert f"{seen['accentFacts']['was']:.2f}" in note, note


@pytest.mark.parametrize("colour", OVER)
def test_a_colour_that_clears_the_floor_is_left_alone(colour: str) -> None:
    """Without this, "always paint the default" scores full marks."""

    seen = _run(_script(), colour)
    assert seen["accentSeen"] == colour
    assert seen["accentNote"] is None, seen["accentNote"]


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_every_template_holds_the_floor(template: str) -> None:
    """The panel is the same panel on all ten, and so is the ground."""

    script = _script(template)
    shipped = _run(script, None, template)
    assert shipped["accentFloor"] == ACCENT_FLOOR
    seen = _run(script, "#0b0f17", template)
    assert contrast_ratio(seen["accentSeen"], shipped["accentGround"]) >= ACCENT_FLOOR
    assert seen["accentNote"]


def test_the_shipped_accent_is_never_moved() -> None:
    """A page nobody has touched must paint exactly what its theme says."""

    for template in sorted(TEMPLATES):
        seen = _run(_script(template), None, template)
        assert seen["accentNote"] is None, template
        assert contrast_ratio(seen["accentSeen"], seen["accentGround"]) >= ACCENT_FLOOR
