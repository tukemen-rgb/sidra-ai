"""The losing streak counts real defeats, and only this round's.

The difficulty eases after three losses (C-1402). It was being fed 「did
any failure beat ever fire?」 over the life of the page, which was wrong
twice:

* The count never reset, so in a template that restarts in place every
  round after the first loss was also a loss - 29 straight duel wins were
  measured as a streak of 30.
* The round clock's own beat made every fishing and catch round a defeat,
  though neither template has a losing state. The buzzer is how those
  games end, not how they are lost, and three rounds of either quietly
  eased the difficulty for somebody who had lost nothing - the exact
  help-for-people-who-don't-need-it §11 事実 3 warns about.

The beat itself is untouched: an ending should still land (C-1105). What
changed is the predicate feeding the record, which is a different thing
that happened to share a variable.
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

from sidra_ai.creation.adapt import streak_probe_source  # noqa: E402
from sidra_ai.creation.games import TEMPLATES, generate_game  # noqa: E402

ASKS = {
    "adventure": "冒険ゲームを作って",
    "catch": "キャッチゲームを作って",
    "duel": "対戦ゲームを作って",
    "fishing": "釣りゲームを作って",
    "kaiju": "怪獣と戦うゲームを作って",
    "marble": "3D のゲームを作って",
    "platformer": "ジャンプアクションを作って",
    "puzzle": "パズルゲームを作って",
    "racing": "レースゲームを作って",
    "shooter": "シューティングゲームを作って",
}

#: Seeded so both directions show in one run: a losing round must reach
#: three, and a winning one must clear it.
SEEDED = 2

#: Pressed every frame, because since C-1123 a round nobody played banks
#: nothing at all - including a defeat. A streak check on an abandoned
#: round would be measuring that rule instead of this one.
#:
#: A key no template binds, deliberately: holding a *steering* key changes
#: how each game goes - ArrowRight drives the race into a wall, so the one
#: template that wins on its own started losing - and this check is about
#: the streak, not about the driving.
PLAYED = "x"


def _play(template: str, rounds: int = 4, hold: str | None = PLAYED) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the rounds")
    found = re.search(
        r"<script>(.*?)</script>", generate_game(ASKS[template]).html, re.S
    )
    assert found is not None
    run = subprocess.run(
        ["node", "-"],
        input=streak_probe_source(
            found.group(1),
            rounds=rounds,
            stored={f"sidra.streak.{template}": SEEDED},
            hold=hold,
        ),
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert run.returncode == 0, run.stderr.strip()[:400]
    seen = json.loads(run.stdout.strip().splitlines()[-1])
    # Only the rounds that really were rounds: a clock-ended template
    # restarts by re-running the page, which a probe cannot do, so the same
    # finished round would otherwise be counted several times over.
    seen["played"] = [row for row in seen["rounds"] if row["fresh"]]
    return seen


def test_every_template_is_covered_by_a_request() -> None:
    assert set(ASKS) == set(TEMPLATES)


@pytest.mark.parametrize("template", sorted(ASKS))
def test_the_failure_count_is_per_round(template: str) -> None:
    """The bug itself: 29 wins measured as a streak of 30."""

    for row in _play(template)["played"]:
        assert row["beats"] <= 1, row


@pytest.mark.parametrize("template", ["fishing", "catch"])
def test_a_game_with_no_losing_state_never_records_a_defeat(template: str) -> None:
    seen = _play(template)

    assert seen["canLose"] is False
    for row in seen["played"]:
        assert row["lost"] is False, row
        assert row["stored"] == 0, row


@pytest.mark.parametrize("template", ["fishing", "catch"])
def test_the_ending_still_lands_for_them(template: str) -> None:
    """Not a defeat is not the same as not an ending (C-1105)."""

    assert any(row["beats"] > 0 for row in _play(template)["played"])


@pytest.mark.parametrize("template", sorted(ASKS))
def test_a_round_that_fired_the_beat_is_recorded_as_a_defeat(template: str) -> None:
    """Checked against the beat rather than the predicate that writes the
    record - a page where nothing is ever a loss agrees with itself."""

    seen = _play(template)
    if not seen["canLose"]:
        pytest.skip("no losing state to record")
    for row in seen["played"]:
        if row["beats"] > 0:
            assert row["lost"] is True, row


@pytest.mark.parametrize("template", sorted(ASKS))
def test_the_streak_follows_the_losses(template: str) -> None:
    seen = _play(template)
    expected = SEEDED if seen["canLose"] else 0

    for row in seen["played"]:
        if seen["canLose"]:
            expected = expected + 1 if row["lost"] else 0
        assert row["stored"] == expected, row


def test_a_won_round_clears_a_seeded_streak() -> None:
    """Racing is the one that finishes untouched, so it is the case that
    can prove a win wipes the count."""

    played = _play("racing")["played"]

    assert played, "racing produced no round"
    assert not any(row["lost"] for row in played)
    assert played[0]["stored"] == 0
