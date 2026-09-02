"""Every go reaches a break, so the game can be put down.

§8 事実 1 of the play notes. A page that runs forever is not endless
content, it is a page with no moment to stop at - and "how long is a go?"
had no answer at all for the two templates with no state machine, and no
bound for the other seven.

Read off the running page, not the source. A constant named
``ROUND_SECONDS`` proves nothing about a loop; what proves it is starting
the page, pressing nothing, and watching for the break. The bug this file
exists to keep out was found exactly that way: the first version cleared
the break as soon as the template looked live again, which is *always*,
because the clock fires precisely when the template has not finished. The
banner lasted a single frame.
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
from sidra_ai.creation.round import (  # noqa: E402
    PREAMBLE_NAMES,
    ROUND_LIVE,
    ROUND_SECONDS,
    live_gaps,
    probe_source,
    states_in,
)

KEYS = sorted(TEMPLATES)
#: The two with no state machine: for them the shared clock is the only
#: ending there is, so they are the templates the item was written for.
ENDLESS = sorted(key for key in KEYS if not ROUND_LIVE.get(key))


def _play(template: str, *, warmup: int = 4) -> dict:
    """Start the page, then leave it alone for longer than the bound."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the page")
    page = generate_game("ゲームを作って", template=template).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(script.group(1), warmup=warmup),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("template", KEYS)
def test_a_go_ends_within_the_bound(template: str) -> None:
    seen = _play(template)

    assert seen["breakAt"] is not None, f"no break in {ROUND_SECONDS}s of play"
    assert seen["breakAt"] <= seen["limit"] + 100, seen["breakAt"] / 1000


@pytest.mark.parametrize("template", ENDLESS)
def test_a_template_with_no_ending_is_ended_by_the_clock(template: str) -> None:
    """The case the item was written for, named rather than incidental."""

    seen = _play(template)

    assert seen["reason"] == "time"
    assert seen["endState"] is None


@pytest.mark.parametrize("template", KEYS)
def test_the_loop_is_held_and_not_dropped(template: str) -> None:
    """A dropped loop is a still image; the page could never be handed back."""

    assert _play(template)["running"] is True


@pytest.mark.parametrize("template", KEYS)
def test_the_title_screen_costs_the_round_nothing(template: str) -> None:
    """Played time, not wall time - the same reason pause is free.

    Ten seconds on the title screen and the break still lands on the bound,
    not ten seconds early.
    """

    idle = _play(template, warmup=600)

    assert idle["gatedMs"] == 0
    if idle["reason"] == "time":
        assert abs(idle["breakAt"] - idle["limit"]) < 100


@pytest.mark.parametrize("template", KEYS)
def test_coming_back_belongs_to_whoever_ended_the_round(template: str) -> None:
    """The clock re-runs the page; a template's own end screen keeps its R.

    Reloading over an end screen would throw away the score it is showing,
    and leaving a clock break with no way out would be worse than no bound.
    """

    seen = _play(template)

    assert seen["reloads"] == (1 if seen["reason"] == "time" else 0)


@pytest.mark.parametrize("template", KEYS)
def test_the_break_does_not_come_early(template: str) -> None:
    """A bound that fired over an unfinished game would be a worse game."""

    seen = _play(template)

    if seen["reason"] == "time":
        assert seen["breakAt"] >= seen["limit"]


# --------------------------------------------------- what the page cannot say


@pytest.mark.parametrize("template", KEYS)
def test_the_live_state_table_matches_the_template(template: str) -> None:
    """A typo here would fire the clock over a game that had finished."""

    assert live_gaps(template, TEMPLATES[template].script) == []


@pytest.mark.parametrize("template", KEYS)
def test_a_template_with_states_declares_which_one_is_playing(template: str) -> None:
    assigned = states_in(TEMPLATES[template].script)

    assert bool(assigned) == bool(ROUND_LIVE[template])
    for name in ROUND_LIVE[template]:
        assert name in assigned


def test_the_bound_is_the_one_the_notes_give() -> None:
    assert ROUND_SECONDS == 60


@pytest.mark.parametrize("template", KEYS)
def test_no_template_shadows_a_clock_name(template: str) -> None:
    """A collision would break only in the generated page."""

    body = TEMPLATES[template].script
    for name in PREAMBLE_NAMES:
        assert f"function {name}(" not in body
        assert f"const {name}=" not in body
        assert f"let {name}=" not in body
