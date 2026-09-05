"""C-1418: the number said where it was earned.

The score has only ever moved as a total in the corner, so which act paid
what was arithmetic the player had to do in their head. A 「+N」 at the place
it happened says it once and gets out of the way.

The risk in a decoration like this is that it lies, so the shape of the code
is chosen to make lying impossible rather than merely unlikely: the call
sites read ``score+=scorePop(x, y, n)``. The float returns the number it
shows, so the number drawn and the number added are one value, not two that
have to be kept in step.

Writing the instrument for this is what found the graze bonus: a near miss
in shooter pays through ``grazeFacts().paid`` rather than through the
template's own ``score``, so the total moved and nothing on screen said why.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.juice import POP_MAX, pop_probe_source

#: Scores steadily with nobody touching it, which is what the probe needs.
TEMPLATE = "catch"

#: Every template that adds to a score, and therefore every one that has to
#: say so. Kept here rather than derived, so wiring a new scoring site
#: without a float is a failing test rather than a silent omission.
SCORERS = ("catch", "fishing", "marble", "puzzle", "shooter")


def _script(template: str) -> str:
    body = re.search(
        r"<script>(.*?)</script>",
        generate_game("ゲームを作って", template=template).html,
        re.S,
    )
    assert body is not None
    return body.group(1)


def _play(template: str = TEMPLATE, **kwargs) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play for points")
    probe = subprocess.run(
        ["node", "-"],
        input=pop_probe_source(_script(template), **kwargs),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:500]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def run() -> dict:
    return _play(frames=1800, stress=POP_MAX + 3)


# --- every payment is wired ------------------------------------------------


@pytest.mark.parametrize("template", SCORERS)
def test_every_scoring_site_says_what_it_paid(template: str) -> None:
    body = _script(template)
    # The comment in the preamble names the call shape too, so the count is
    # of real call sites: one more than the templates that have none.
    calls = len(re.findall(r"score\+=scorePop\(", body))
    assert calls >= 2, f"{template} adds to a score without floating it"


def test_a_template_with_no_score_wires_nothing() -> None:
    # racing is scored by laps completed, so it has no per-event payment to
    # announce. Only the preamble's own comment mentions the call.
    assert len(re.findall(r"score\+=scorePop\(", _script("racing"))) == 1


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_the_float_reaches_every_page(template: str) -> None:
    body = _script(template)
    assert "function scorePop(" in body
    assert "stepPops()" in body


# --- what a whole go looks like --------------------------------------------


def test_the_sum_of_what_it_said_is_what_was_scored(run: dict) -> None:
    # 条件③, end to end. This is the check that found the graze bonus.
    assert run["end"]["total"] == run["frames"][-1]["score"]
    assert run["end"]["shown"] > 0


def test_what_it_holds_is_what_it_paints(run: dict) -> None:
    # On every frame that redrew. A frozen frame - the juice kit's hitstop -
    # paints nothing at all and keeps the previous picture, floats included.
    for frame in run["frames"]:
        if frame["all"]:
            assert sorted(frame["painted"]) == sorted(f"+{n}" for n in frame["said"])


def test_the_screen_is_never_papered(run: dict) -> None:
    assert max(f["live"] for f in run["frames"]) <= POP_MAX


def test_the_cap_is_a_number_that_has_been_seen_to_engage(run: dict) -> None:
    # No natural run scores fast enough to reach it, so the page's own
    # function is asked directly for more than it will hold.
    stress = run["stress"]
    assert stress["asked"] == POP_MAX + 3
    assert stress["after"]["live"] == POP_MAX
    assert stress["painted"] == POP_MAX
    assert stress["after"]["dropped"] - stress["before"]["dropped"] == stress["asked"] - POP_MAX


def test_reduced_motion_gets_no_floats_but_still_scores() -> None:
    quiet = _play(frames=1800, reduced=True)
    assert quiet["end"]["shown"] == 0
    assert not [f for f in quiet["frames"] if f["painted"]]
    # The points still go in - the float is a decoration, not the mechanism.
    assert quiet["frames"][-1]["score"] > 0


def test_a_zero_or_negative_payment_says_nothing() -> None:
    # Guarded at the top of scorePop: 「+0」 is noise, and a negative would
    # need a different word than 「+」.
    body = _script(TEMPLATE)
    assert "if(typeof n!=='number'||!isFinite(n)||n<=0)return n;" in body
