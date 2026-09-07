"""A round that beat nothing is not a personal best (C-1502, 第1回批評 #11).

The first round is always a record - there is nothing to beat - so the strip
congratulated a player on the worst run the game can produce. Measured on the
real pages before any of this was written: duel 「与ダメージ 0 / 自己ベスト
更新」, fishing 「得点 0 / 自己ベスト更新」, platformer 「宝石 0 / 自己ベスト
更新」.

Two directions, and the second is not decoration. The obvious fix is a
condition on the cheer, and the obvious condition is too wide: the item asked
for defeats to be excluded as well, and driving that against the real pages
took the record away from shooter 得点 54, puzzle 得点 36, adventure 宝石 1 and
marble スコア 1 - because most of these templates END in defeat by design.
A round you scored in and then lost is still your best round. So these tests
pin both halves: the zero stays quiet AND the score still celebrates.

What is withheld is the congratulation, never the record. 0 is still written,
still ghosted, still what the next round has to beat.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.round import probe_source

CHEER = "自己ベスト更新"


def drive(template: str):
    page = generate_game("ゲームを作って", template=template).html
    body = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    done = subprocess.run(
        ["node", "-"],
        input=probe_source(body, hold=" ", frames=8000),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr[-600:]
    out = json.loads(done.stdout.strip().splitlines()[-1])
    out["said"] = any(CHEER in line for line in out.get("strip", []))
    return out


@pytest.fixture(scope="module")
def runs():
    return {key: drive(key) for key in sorted(TEMPLATES)}


def banked(runs):
    return [r for r in runs.values() if r["record"] and r["score"] is not None]


# ------------------------------------------------------------ the defect


def test_a_first_round_that_scored_nothing_is_not_congratulated(runs) -> None:
    zeros = [r for r in banked(runs) if r["score"] <= 0]
    assert zeros, "no run ended on zero - the defect cannot be observed"
    for run in zeros:
        assert not run["said"], run["strip"]


def test_the_zero_round_still_says_something_honest(runs) -> None:
    """Silence is not the fix - the strip keeps the line it already had."""

    zeros = [r for r in banked(runs) if r["score"] <= 0]
    for run in zeros:
        assert any("自己ベスト" in line for line in run["strip"]), run["strip"]


# ------------------------------------------------------- the other half


def test_a_first_round_that_scored_is_still_congratulated(runs) -> None:
    """The overcorrection, pinned.

    Without this, a build that silenced the cheer entirely would satisfy
    every assertion above and read as a fix.
    """

    scored = [r for r in banked(runs) if r["score"] > 0]
    assert len(scored) >= 5, [r["template"] for r in scored]
    for run in scored:
        assert run["said"], (run["template"], run["score"], run["strip"])


def test_losing_with_points_is_still_a_personal_best(runs) -> None:
    """Most templates end in defeat by design; that must not silence them."""

    lost_but_scored = [
        r for r in banked(runs) if r["score"] > 0 and r.get("lost")
    ]
    assert lost_but_scored, "no template both scored and lost - widen the drive"
    for run in lost_but_scored:
        assert run["said"], (run["template"], run["score"])


# -------------------------------------------------------- the record itself


def test_the_zero_is_still_banked(runs) -> None:
    """The congratulation is withheld; the record is not.

    A zero that stopped being written would make the next round a first
    round forever, and 「あと 1」 would never have anything to count from.
    """

    zeros = [r for r in banked(runs) if r["score"] <= 0]
    for run in zeros:
        assert run["record"] is True
        assert run["best"] == 0


def test_the_page_reports_the_two_readings_apart(runs) -> None:
    """``record`` and ``cheer`` are different facts and stay different."""

    for run in banked(runs):
        assert run["record"] is True
        assert run["cheer"] is (run["score"] > 0)
