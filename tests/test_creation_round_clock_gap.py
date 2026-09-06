"""Time nobody could play must not be charged to the round (C-1450).

``requestAnimationFrame`` stops while a tab is hidden, and the round clock
read the raw difference between timestamps - so the first frame back
carried the whole absence at once. A minute in another tab arrived as a
minute of the go, buzzer and failure beat included, for a round the player
never touched.

The neighbour already had the answer: ``music.py`` re-anchors its scheduler
with ``if(MUSIC_NEXT<0||now-MUSIC_NEXT>1){MUSIC_NEXT=now}``. Same second,
same reason - so the threshold is taken from the codebase rather than from
taste.

Both directions are the point. "Forgive the gap" has an obvious wrong
version: a clock that forgave every hitch would drift away from the wall
clock until 「60 秒」 meant nothing. So the tests below check that a long
absence costs nothing AND that a short one still costs exactly itself.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.round import ROUND_GAP_MS, clock_probe_source

HOLD = {"racing": "ArrowLeft"}

#: Ten seconds into a played go: far from the start and far from the buzzer,
#: so neither end is what is being read.
GAP_AT = 600
AWAY_MS = 60_000
HITCH_MS = ROUND_GAP_MS // 2
#: One frame at 60fps. Two runs of the same page can differ by the frame the
#: gap displaced, never by more.
SLACK = 17

#: Templates whose go is ended by the buzzer rather than by themselves, so
#: the clock is actually the thing under test.
REACHES_THE_BUZZER = ("catch", "fishing", "platformer")


def drive(template: str, **kw):
    page = generate_game("ゲームを作って", template=template).html
    body = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    done = subprocess.run(
        ["node", "-"],
        input=clock_probe_source(body, hold=HOLD.get(template, ""), **kw),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr[-600:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def ends(run):
    for index, frame in enumerate(run["frames"]):
        if frame["done"]:
            return index, frame["reason"]
    return None, None


@pytest.fixture(scope="module")
def runs():
    out = {}
    for key in REACHES_THE_BUZZER:
        out[key] = {
            "plain": drive(key),
            "away": drive(key, gap_ms=AWAY_MS, gap_at=GAP_AT),
            "hitch": drive(key, gap_ms=HITCH_MS, gap_at=GAP_AT),
        }
    return out


@pytest.mark.parametrize("template", REACHES_THE_BUZZER)
def test_the_buzzer_is_what_ends_these_gos(template, runs):
    # Without this the rest would be measuring a template that finishes on
    # its own, where the clock never gets a say.
    at, why = ends(runs[template]["plain"])
    assert why == "time"
    assert at is not None and at > GAP_AT


@pytest.mark.parametrize("template", REACHES_THE_BUZZER)
def test_a_minute_in_another_tab_costs_the_round_nothing(template, runs):
    plain, away = runs[template]["plain"], runs[template]["away"]
    assert ends(away) == ends(plain)


@pytest.mark.parametrize("template", REACHES_THE_BUZZER)
def test_the_remaining_time_does_not_jump_when_the_tab_comes_back(template, runs):
    """Not only the ending: every frame after the absence still agrees.

    A page that lost the minute and then somehow ended on the same frame
    would still have shown the player a clock that leapt.
    """

    plain, away = runs[template]["plain"], runs[template]["away"]
    at, _ = ends(plain)
    drift = max(
        abs(away["frames"][i]["ms"] - plain["frames"][i]["ms"])
        for i in range(GAP_AT + 1, at)
    )
    assert drift <= SLACK, drift


@pytest.mark.parametrize("template", REACHES_THE_BUZZER)
def test_a_hitch_below_the_threshold_is_still_charged(template, runs):
    """The other direction, and the one that keeps the clock a clock.

    A guard that forgave everything would pass every test above while
    quietly making the round last as long as the player liked.
    """

    plain, hitch = runs[template]["plain"], runs[template]["hitch"]
    plain_at, _ = ends(plain)
    hitch_at, _ = ends(hitch)
    assert hitch_at is not None and hitch_at < plain_at
    # Read shortly after the hitch, while both runs are still going: past
    # the buzzer the remaining time is clamped at 0 in both, so a late frame
    # would report "no difference" no matter what the guard did.
    charged = (
        plain["frames"][GAP_AT + 60]["ms"] - hitch["frames"][GAP_AT + 60]["ms"]
    )
    assert charged >= HITCH_MS * 0.8, charged


def test_the_threshold_is_the_one_the_neighbour_already_uses():
    """1000ms, and not a number somebody liked the look of.

    music.py re-anchors its scheduler on a one-second gap - in AudioContext
    seconds, which is why the literal there is ``1``. Reading it here keeps
    the two from drifting apart silently.
    """

    from sidra_ai.creation.music import MUSIC_PREAMBLE

    assert ROUND_GAP_MS == 1_000
    assert "now-MUSIC_NEXT>1" in MUSIC_PREAMBLE


def test_hitstop_does_not_reach_the_threshold():
    """The guard must not be quietly forgiving the juice kit.

    hitstop withholds the DRAWING for a few frames; the loop keeps running
    at frame pace. Read off a driven page rather than assumed: the largest
    step between consecutive frames of a played go stays at frame scale.
    """

    run = drive("platformer")
    steps = [
        run["frames"][i + 1]["clock"] - run["frames"][i]["clock"]
        for i in range(len(run["frames"]) - 1)
    ]
    assert max(steps) < ROUND_GAP_MS, max(steps)


def test_the_clock_still_runs_when_nothing_is_hidden():
    """The whole minute, unforgiven, when there is nothing to forgive."""

    run = drive("catch")
    at, why = ends(run)
    assert why == "time"
    # 60 seconds at 60fps, give or take the frame the buzzer landed on.
    assert 3590 <= at <= 3610, at
