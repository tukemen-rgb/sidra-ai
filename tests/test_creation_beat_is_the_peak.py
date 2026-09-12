"""The round's beat is the round's peak (§8 事実 2, C-1717).

§8 事実 2 records the GDC demo's finding that 「失敗時の派手なフィード
バックがリトライ意欲に直結」, and 「増幅する」 is a comparative: amplified
against what? Nothing compared. ``creation_fail_beat`` asks whether the
beat fires, once, and survives reduced motion. ``creation_win_beat``
compares a single dial - shake 16 against the failure's 14 - and leaves
the hold (7 against 7) and the particles (26 against 20) alone.

Measured before fixed: fishing's perfect catch threw 22 particles against
the failure beat's 20, while shaking 6 against 14 and holding 3 against 7.
Staged, the maze's guardian died in 32 - over even the win beat's 26 -
with a shake of 12 and a hold of 6 that both sat under the failure's. The
particle channel was the only one not following the order the other two
already stated, so the counts were brought into line rather than a new
design decision being made: 32→18, 22→18, and the charm pickup's 20→16,
a pickup with no shake and no hold at all that threw as many particles as
losing the round.

``failBeat`` and ``winBeat`` are wrapped so the beat's own calls and the
round's ordinary juice are told apart exactly. Per frame would not do it:
a loss lands on the same frame as the blow that caused it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.juice import CHARM_STAGE, GUARDIAN_STAGE, beat_peak_probe

REQUESTS = {
    "adventure": "迷宮を冒険するゲームを作って",
    "duel": "ビームで撃ち合うゲームを作って",
    "kaiju": "巨大怪獣と戦うゲームを作って",
    "shooter": "シューティングゲームを作って",
    "puzzle": "パズルゲームを作って",
    "platformer": "ジャンプで進むゲームを作って",
    "marble": "玉転がしゲームを作って",
    "racing": "レースゲームを作って",
    "fishing": "釣りゲームを作って",
    "catch": "落ちものをキャッチするゲームを作って",
}
DIALS = ("shake", "hold", "parts")


def read(key: str, stage: str = "") -> dict:
    found = re.search(r"<script>(.*?)</script>", generate_game(REQUESTS[key]).html, re.S)
    assert found is not None, key
    got = subprocess.run(
        ["node", "-"],
        input=beat_peak_probe(found.group(1), stage=stage),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert got.returncode == 0, (key, got.stderr[:400])
    return json.loads(got.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def rounds() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the rounds")
    return {key: read(key) for key in REQUESTS}


@pytest.fixture(scope="module")
def guarded() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the rounds")
    return read("adventure", GUARDIAN_STAGE + CHARM_STAGE)


def which_beat(seen: dict) -> str:
    assert seen["fails"] or seen["wins"], "the round never ended"
    return "fail" if seen["fails"] else "win"


@pytest.mark.parametrize("key", sorted(REQUESTS))
def test_the_round_ends_so_there_is_something_to_compare(
    rounds: dict, key: str
) -> None:
    assert rounds[key]["fails"] or rounds[key]["wins"], rounds[key]


@pytest.mark.parametrize("key", sorted(REQUESTS))
def test_the_beat_outweighs_the_round_on_every_dial(rounds: dict, key: str) -> None:
    seen = rounds[key]
    beat = seen["peak"][which_beat(seen)]
    play = seen["peak"]["play"]
    for dial in DIALS:
        assert beat[dial] > play[dial], (key, dial, beat[dial], play[dial])


def test_the_moments_the_pilot_never_reaches_are_measured(guarded: dict) -> None:
    """The largest burst sits where an ignorant pilot never goes, and so
    does the charm behind the optional door. A contract that misses the
    largest one is not a contract - and the first version of this judge
    proved it by missing the charm until that was staged too."""

    play = guarded["peak"]["play"]
    assert play["shake"] > 0, "the guardian fight was never staged"
    beat = guarded["peak"][which_beat(guarded)]
    for dial in DIALS:
        assert beat[dial] > play[dial], (dial, beat[dial], play[dial])


def test_the_particle_counts_follow_the_order_the_other_dials_state() -> None:
    """The three numbers that disagreed, named where they live."""

    from sidra_ai.creation import adventure, games

    assert "burst(guard.x,guard.y,18,'ALERT_JUICE');" in adventure.ADVENTURE_SCRIPT
    assert "burst(hero.x,hero.y,16,'ALERT_JUICE')}" in adventure.ADVENTURE_SCRIPT
    assert ",32,'ALERT_JUICE'" not in adventure.ADVENTURE_SCRIPT
    assert "cv.height/2,18,'ACCENT_JUICE')}" in games._FISHING
    assert "cv.height/2,22,'ACCENT_JUICE')}" not in games._FISHING
