"""A round ends by the template OR by the clock - probes must ask both (C-1506).

The report was that driving fishing for 6000 frames left ``roundEnded()``
false the whole way while the clock had long since fired. Driven here, that
is not a hole in either the product or the observation - it is what
``roundEnded()`` means:

    function roundEnded(){return ROUND_LIVE.length>0&&!roundLive()}

fishing and catch declare **no** live states (``ROUND_LIVE`` is empty), so
"the template reached its own ending" is false for them by construction.
Their rounds end on the buzzer, and ``ROUND_DONE`` is what says so.

What the investigation did find is on the instrument side, and it was wider
than the report: two probes broke their drive loop on ``roundEnded()``
alone, and that break fired on **no template at all**. The buzzer arrives
first, the wrapper then stops calling the template's frame, and the template
is frozen in a live state - so every run exhausted its 4000-iteration guard
and worked only because the guard outlasted the round. These tests pin the
pair, so a guard that is later trimmed cannot quietly start measuring
unfinished rounds.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

import re as _re

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.round import ROUND_LIVE, history_probe_source

#: The two with no ending of their own, and three that have one.
NO_END_STATE = ("fishing", "catch")
HAS_END_STATE = ("duel", "racing", "shooter")


def drive(template: str) -> dict:
    page = generate_game("ゲームを作って", template=template).html
    body = _re.search(r"<script>(.*?)</script>", page, _re.S).group(1)
    source = history_probe_source(body).replace(
        "console.log(JSON.stringify({\n  score: facts.score",
        "console.log(JSON.stringify({\n  guard: guard, done: !!facts.done,"
        "\n  score: facts.score",
    )
    done = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=300
    )
    assert done.returncode == 0, done.stderr[-600:]
    return json.loads(done.stdout.strip().splitlines()[-1])


# --------------------------------------------------- what roundEnded means


@pytest.mark.parametrize("template", NO_END_STATE)
def test_a_template_with_no_end_state_declares_none(template: str) -> None:
    """The reported behaviour, explained at its source rather than guessed."""

    assert ROUND_LIVE.get(template, ()) == ()


@pytest.mark.parametrize("template", HAS_END_STATE)
def test_a_template_with_an_ending_declares_its_live_states(template: str) -> None:
    assert ROUND_LIVE.get(template, ())


# ------------------------------------------------------ the instrument fix


@pytest.mark.parametrize("template", NO_END_STATE + HAS_END_STATE)
def test_the_drive_loop_stops_at_the_end_not_at_the_guard(template: str) -> None:
    """The guard has to be a guard, not the exit.

    Before this, every template ran all 4000 iterations because the break
    asked only ``roundEnded()``. A loop that always reaches its guard is a
    loop whose results depend on the guard being generous.
    """

    run = drive(template)
    assert run["done"] is True, "the round never finished"
    assert run["guard"] < 1000, run["guard"]


@pytest.mark.parametrize("template", NO_END_STATE + HAS_END_STATE)
def test_the_measured_result_is_unchanged_by_stopping_earlier(
    template: str,
) -> None:
    """Stopping at the buzzer must not cost the round its bank.

    The strip is what banks, and it draws in the steps after the loop; if
    the earlier exit skipped that, the run row would come back empty.
    """

    run = drive(template)
    assert run["runs"], run
    assert run["score"] is not None
