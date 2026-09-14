"""The round-sky judge must cover every template whose act steps on the clock.

§7 観察 5-6 at round scale: the sky steps with played time, the final act is
the brightest, and the sixty seconds still end the go. ``creation_round_scene``
measures that - and for a long time it measured fishing, catch and puzzle while
saying nothing at all about the other seven.

The shooter had carried the same contract since C-1315. Its page says so above
``ACT`` ("the 60-second round in three acts ... the final third is the
brightest sky of the fight") and ``setPal``'s third act holds the same +0.22
the other three hold. The only thing that kept it out of the table is how it is
spelled: fishing, catch and puzzle write the act inline as
``ROUND_MS/(ROUND_LIMIT_MS/3)``, and the shooter factored the identical thirds
into ``actOf()``. Nothing failed when it drifted out of view, because a judge
that names three templates and stays quiet about the rest cannot fail that way
(C-1795, the caller-side form of C-1755).

So the split is read off the pages rather than asserted in prose: a sentence
saying "the other six are different" keeps looking true after someone changes
one. These tests pin the reader that does that reading.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.games import TEMPLATES, generate_game  # noqa: E402
from sidra_ai.evals.round_scene import ELSEWHERE, clock_bound  # noqa: E402
from sidra_ai.creation.shooter import PROBE, scene_probe  # noqa: E402

#: The judge's own reader, imported rather than copied. The first draft of
#: this file carried its own copy of `clock_bound` and its own template
#: lists: sabotaging the judge changed nothing and all fourteen tests went
#: on passing, because they were exercising a reader nobody used. That is
#: C-1793's single source, and C-1755's lesson wearing a test's clothes.
CLOCK_BOUND = {"catch", "fishing", "puzzle", "shooter"}


def script_of(template: str) -> str:
    page = generate_game("ゲームを作って", template=template).html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None, f"{template} has no script"
    return found.group(1)


def test_every_template_is_either_measured_here_or_named_elsewhere() -> None:
    """No template may be absent from both lists - that is how one hides."""

    assert CLOCK_BOUND | set(ELSEWHERE) == set(TEMPLATES)
    assert not (CLOCK_BOUND & set(ELSEWHERE))


@pytest.mark.parametrize("template", sorted(CLOCK_BOUND))
def test_the_clock_bound_templates_really_are(template: str) -> None:
    assert clock_bound(script_of(template)), (
        f"{template} is in the judge's table but its act no longer reads the clock"
    )


@pytest.mark.parametrize("template", sorted(ELSEWHERE))
def test_the_others_really_do_step_on_something_else(template: str) -> None:
    """The half that catches a template quietly joining the clock.

    This is the failure that produced the item: the shooter became
    clock-bound and the judge never noticed, because nothing was watching
    the templates it had not listed.
    """

    assert not clock_bound(script_of(template)), (
        f"{template} now steps its act on the clock and belongs in the table"
    )


def test_the_helper_spelling_does_not_hide_a_clock() -> None:
    """`actOf()` and the inline form must read the same to this reader.

    Being spelled differently is the entire mechanism of C-1795, so the
    reader has to resolve one level of helper or it re-creates the bug.
    """

    assert clock_bound("setScene(actOf());function actOf(){return t>=ACT*2?2:0}")
    assert clock_bound("setScene(Math.min(2,ROUND_MS/(ROUND_LIMIT_MS/3)))")
    assert not clock_bound("setScene(actOf());function actOf(){return ball.z>=C?2:0}")
    assert not clock_bound("function setScene(i){SCENE=i|0}")


def test_the_shooter_round_reaches_the_buzzer_with_both_skies_played() -> None:
    """What the new probe is for, driven for real.

    A palette that exists is not a round that is still playable in the act
    it is brightest in - C-1640 passed a page pinned to act 0 by reading
    only the colour table.
    """

    page = generate_game("シューティングゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    out = subprocess.run(
        ["node", "-"], input=scene_probe(script),
        capture_output=True, text=True, timeout=300,
    )
    assert out.returncode == 0, out.stderr[:400]
    got = json.loads(out.stdout.strip().splitlines()[-1])

    assert (got["sceneEarly"], got["sceneMid"], got["sceneLate"]) == (0, 1, 2)
    assert got["sceneOrder"] == [0, 1, 2]
    lums = [s["lum"] for s in got["scenes"]]
    assert lums.index(max(lums)) == len(lums) - 1, "the last sky is not the brightest"
    assert got["killEarly"] == 1 and got["killLate"] == 1
    assert got["done"] and got["reason"] == "time", "the sky touched the break"


def test_the_two_probes_fly_one_pilot() -> None:
    """The flight is shared, not copied - a second copy would drift apart."""

    from sidra_ai.creation.shooter import _PILOT_JS

    assert _PILOT_JS in PROBE
    assert _PILOT_JS in scene_probe("")
