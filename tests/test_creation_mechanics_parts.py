"""The first mechanic two templates run out of the same code.

§9 学び (3) says the N-templates approach stops scaling, and the answer is
supposed to be parts. C-1114 measured what the nine templates actually
share before designing any, and the measurement is the interesting part:
27 identical non-trivial lines across ~1000, and the most-shared of them
are infrastructure rather than mechanics. Exactly one of the four
mechanics the plan names was duplicated in a liftable form - steering
along x with a clamp, written out four times.

These tests hold the PoC to being a real substitution rather than a
rename: the part is what moves the actor in the two templates wired to
it, the two that are not wired are untouched (so the "before" is still in
the tree), and the behaviour is identical because the keys, the speed and
the margins did not change.

``docs/research/mechanics-parts.md`` carries the finding this file cannot:
the other three mechanics are not shared because there is no coordinate
contract and no entity contract, so combining parts is contract work
before it is extraction work.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.games import TEMPLATES, generate_game  # noqa: E402
from sidra_ai.creation.parts import (  # noqa: E402
    CONTRACT_GAPS,
    PARTS_PREAMBLE,
    PREAMBLE_NAMES,
    UNWIRED,
    WIRED,
)
from sidra_ai.creation.together import probe_source  # noqa: E402
from sidra_ai.creation.tuning import SPEED_BINDING  # noqa: E402

KEYS = sorted(TEMPLATES)
#: The four that steer. Two are wired to the part, two are not - and the
#: contrast is what makes "the part is doing the moving" checkable.
STEERS = ("kaiju", "racing", "shooter", "platformer")


def _play(template: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the part")
    found = re.search(
        r"<script>(.*?)</script>", generate_game("ゲームを作って", template=template).html, re.S
    )
    assert found is not None
    source = probe_source(
        found.group(1),
        speed_expr=SPEED_BINDING[template],
        stored={f"sidra.seen.{template}": "1"},
    )
    source = source.replace(
        "  writes: [...new Set(allWrites)].sort(),",
        "  writes: [...new Set(allWrites)].sort(), parts: partsFacts(),",
    )
    probe = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=300
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


# ------------------------------------------------------------------ the PoC


@pytest.mark.parametrize("template", WIRED)
def test_the_part_is_what_moves_the_actor(template: str) -> None:
    """Not a rename: the shared function ran, many times, during real play."""

    assert _play(template)["parts"]["moves"] > 0


@pytest.mark.parametrize("template", sorted(UNWIRED))
def test_the_templates_not_wired_yet_are_untouched(template: str) -> None:
    """The "before" stays in the tree, so the contrast is observable.

    Each has a reason it is more than a substitution, and the reason is
    recorded rather than left as an omission.
    """

    assert _play(template)["parts"]["moves"] == 0
    assert UNWIRED[template]


@pytest.mark.parametrize("template", WIRED)
def test_the_wired_templates_still_play(template: str) -> None:
    """The condition C-1114 set for itself: nothing measured may drop."""

    seen = _play(template)

    assert seen["atBreak"]["round"]["done"] or seen["atBreak"]["round"]["ended"]
    assert seen["facts"]["round"]["score"] is not None


@pytest.mark.parametrize("template", WIRED)
def test_the_template_no_longer_carries_its_own_copy(template: str) -> None:
    body = TEMPLATES[template].script

    assert "partsSteerX(" in body
    # The hand-written clamp is gone. The arrow key *names* may well still
    # be here: racing keeps them to preventDefault the page scroll, which
    # is a browser concern rather than a mechanic, and the part does not
    # claim it.
    assert ".x=Math.max(" not in body, "the old hand-written steering is still here"
    assert ".x=Math.min(" not in body


@pytest.mark.parametrize("template", STEERS)
def test_the_wiring_is_declared_either_way(template: str) -> None:
    assert (template in WIRED) != (template in UNWIRED)


# --------------------------------------------------------------- the contract


def test_a_part_reads_input_through_the_page() -> None:
    """A template that kept its keys private could not be recombined with
    anything, so the part must not reach into one."""

    assert "PARTS_KEYS" in PARTS_PREAMBLE
    # The three ways a template reads its own keys. None of them may appear
    # here: a part that reached into one would only work in that template.
    for private in ("K('", "keys[e.key", "keys['"):
        assert private not in PARTS_PREAMBLE


def test_the_part_takes_its_differences_as_arguments() -> None:
    """Speed, margin and key aliases were the only differences between the
    four hand-written copies."""

    assert "partsSteerX(actor,speed,lo,hi,left,right)" in PARTS_PREAMBLE


def test_the_gaps_that_have_to_close_before_a_fifth_caller() -> None:
    """The measurement C-1114 exists to produce.

    Three of the four mechanics named in the plan are not shared because
    the templates disagree about coordinates, about the shape of a thing
    in the world, and about whether there is a loop to end.
    """

    named = {name for name, _ in CONTRACT_GAPS}

    assert {"coordinates", "entities", "the loop"} <= named
    for _, why in CONTRACT_GAPS:
        assert len(why) > 40, "a gap with no explanation is a heading"


def test_the_design_note_is_in_the_tree() -> None:
    note = Path(__file__).resolve().parents[1] / "docs/research/mechanics-parts.md"

    assert note.exists()
    text = note.read_text(encoding="utf-8")
    assert "27" in text, "the measurement is the point of the note"
    assert "契約" in text


@pytest.mark.parametrize("template", KEYS)
def test_no_template_shadows_a_part_name(template: str) -> None:
    body = TEMPLATES[template].script
    for name in PREAMBLE_NAMES:
        assert f"function {name}(" not in body
        assert f"const {name}=" not in body
        assert f"let {name}=" not in body
