"""How many days running the shared board was taken (C-1442).

§8 事実 4: what brings people back is a shared attempt. The daily switch
(C-1107) gives everyone the same board on the same day; this is the only
number in the page about coming *back* rather than about a round.

Days are page loads. The stamp is read once at load and never again -
daily.py's "Not a clock", so a page left open past midnight keeps the day
it started - which means a run of days is a run of PROCESSES with only
the store carried between them. Simulating midnight inside one page would
be measuring a page that cannot exist. Same shape as C-1432's row of
runs, and for the same reason.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.daily import (
    PREAMBLE_NAMES,
    preamble_for,
    streak_probe_source,
)
from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.together import STORAGE_PREFIXES

REQUEST = "ゲームを作って"


def _walk(
    template: str,
    days: list[str],
    *,
    daily: bool = True,
    hold: str | None = "ArrowRight",
) -> list[dict]:
    """Load the page once per day, carrying only the store between loads."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the days out")
    page = generate_game(REQUEST, template=template).html
    body = re.search(r"<script>(.*?)</script>", page, re.S)
    assert body is not None
    store: dict = (
        {f"sidra.tune.{template}": json.dumps({"daily": True})} if daily else {}
    )
    walked = []
    for stamp in days:
        ran = subprocess.run(
            ["node", "-"],
            input=streak_probe_source(body.group(1), stamp=stamp, store=store, hold=hold),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert ran.returncode == 0, ran.stderr[:400]
        seen = json.loads(ran.stdout.strip().splitlines()[-1])
        store = seen["store"]
        walked.append(seen)
    return walked


def _said(day: dict) -> str:
    return day["said"][0] if day["said"] else ""


def test_three_days_running_count_up_and_reach_the_strip() -> None:
    run = _walk("adventure", ["2026-09-01", "2026-09-02", "2026-09-03"])

    assert [d["after"]["shown"] for d in run] == [1, 2, 3]
    # Not on the first: 「1 日目」 would be today wearing a streak's hat,
    # the same reason the row of runs waits for a second run (C-1432).
    assert "日目" not in _said(run[0])
    assert "（2 日目）" in _said(run[1])
    assert "（3 日目）" in _said(run[2])


def test_a_missed_day_starts_again_and_says_so() -> None:
    """No grace day. A count that survived a gap would have stopped
    meaning what it says, which is the one thing a number like this has
    to keep (§9)."""

    run = _walk("adventure", ["2026-09-01", "2026-09-02", "2026-09-05"])

    assert [d["after"]["shown"] for d in run] == [1, 2, 1]
    assert "日目" not in _said(run[-1])


def test_a_second_go_the_same_day_neither_adds_nor_takes_away() -> None:
    """Asked of a streak that has already built.

    From zero this cannot tell "held at 1" from "reset to 1" - measured:
    dropping the once-a-day guard leaves [1, 1, 2] looking perfect, and
    only shows up here, as [1, 2, 1, 2].
    """

    run = _walk("adventure", ["2026-09-01", "2026-09-02", "2026-09-02", "2026-09-03"])

    assert [d["after"]["shown"] for d in run] == [1, 2, 2, 3]


def test_with_the_switch_off_there_is_nothing_to_have_taken() -> None:
    run = _walk("adventure", ["2026-09-01", "2026-09-02"], daily=False)

    assert [d["after"]["shown"] for d in run] == [0, 0]
    assert all(not any(k.startswith("sidra.daily.") for k in d["store"]) for d in run)
    assert all("今日の挑戦" not in _said(d) for d in run)


def test_a_round_nobody_played_is_not_a_day_you_came_back() -> None:
    """Measured on a clock-bound template, so the round really does end
    without a hand on it - and it scores, which is what makes the refusal
    mean something. The same page played is the contrast."""

    idle = _walk("catch", ["2026-09-01", "2026-09-02"], hold=None)

    assert [d["touched"] for d in idle] == [False, False]
    assert [d["after"]["shown"] for d in idle] == [0, 0]

    played = _walk("catch", ["2026-09-01", "2026-09-02"])

    assert [d["touched"] for d in played] == [True, True]
    assert [d["after"]["shown"] for d in played] == [1, 2]


def test_the_day_is_the_one_the_page_loaded_on() -> None:
    """The same reading the board uses, so the count and the board can
    never disagree about what day it is."""

    run = _walk("adventure", ["2026-09-01"])

    assert run[0]["stamp"] == "2026-09-01"
    assert run[0]["after"]["stored"]["day"] == run[0]["after"]["day"]


def test_this_is_not_the_other_streak() -> None:
    """adapt.py counts losses in a row and a win clears it - a rescue,
    not a habit. Different key, different question, and a page carries
    both without either reading the other's."""

    page = generate_game(REQUEST, template="adventure").html

    assert "'sidra.daily.'" in page
    assert "'sidra.streak.'" in page
    assert STORAGE_PREFIXES["sidra.daily."] != STORAGE_PREFIXES["sidra.streak."]


def test_the_key_is_declared_and_the_names_are_the_preamble_s() -> None:
    assert "sidra.daily." in STORAGE_PREFIXES
    for name in ("dailyStreak", "dailyStreakBank", "dailyStreakFacts", "dailyDay"):
        assert name in PREAMBLE_NAMES
        # ...and no template defines one of its own, which would break
        # only in the generated page.
        assert not any(f"function {name}(" in spec.script for spec in TEMPLATES.values())


def test_each_page_keeps_its_own_count() -> None:
    """Two generated games are two artifacts; a streak on one is not a
    streak on the other."""

    keys = set()
    for template in ("adventure", "catch"):
        page = generate_game(REQUEST, template=template).html
        found = re.search(r"const DAILY_STREAK_KEY='sidra\.daily\.'\+(\".*?\")", page)
        assert found is not None, template
        keys.add(found.group(1))

    assert len(keys) == 2
    # and the token really was filled in
    assert "DAILY_NAME_TOKEN" not in preamble_for("adventure")
