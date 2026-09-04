"""A best that can still be beaten.

Four templates score against a ceiling: laps out of three, damage out of
three, cycles out of three, the gems a room holds. The first good run
reaches it, the strip says 自己ベスト更新 once, and after that nothing it
offers is reachable - 「あと 1」 against a maximum is a target that does
not exist.

Each now carries a second key, consulted **only when the scores are
level**: the race that took less time, the duel won with more left. The
score is still the score; this breaks ties, it does not outrank them.

Driven by seeding the store rather than by playing well - the run is given
a best equal to what it will score and a second key that is deliberately
worse, then deliberately better. A saturating record cannot pass both.
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
from sidra_ai.creation.games import generate_game  # noqa: E402
from sidra_ai.creation.round import ROUND_SCORE, ROUND_TIE  # noqa: E402
from sidra_ai.creation.together import STORAGE_PREFIXES  # noqa: E402

ASKS = {
    "racing": "レースゲームを作って",
    "duel": "対戦ゲームを作って",
    "kaiju": "怪獣と戦うゲームを作って",
    "adventure": "冒険ゲームを作って",
}

_EXTRA = """    stored: Number(store[ADAPT_KEY] === undefined ? 0 : store[ADAPT_KEY]),
    score: ROUND_FINAL, tie: roundTieFacts() });"""


def _round(template: str, seed: dict | None = None) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the rounds")
    found = re.search(
        r"<script>(.*?)</script>", generate_game(ASKS[template]).html, re.S
    )
    assert found is not None
    source = streak_probe_source(
        found.group(1), rounds=1, hold="x", stored=seed or {}
    ).replace(
        "    stored: Number(store[ADAPT_KEY] === undefined ? 0 : store[ADAPT_KEY]) });",
        _EXTRA,
    )
    run = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=240
    )
    assert run.returncode == 0, run.stderr.strip()[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])["rounds"][0]


def test_the_second_key_is_declared_storage() -> None:
    """Every key the pages write is written down (C-1118's contract)."""

    assert "sidra.tie." in STORAGE_PREFIXES


def test_only_the_capped_templates_carry_one() -> None:
    """A template whose score has no ceiling has nothing to break a tie
    about, and giving it one would be a second scoreboard."""

    assert set(ROUND_TIE) <= set(ROUND_SCORE)
    assert set(ROUND_TIE) == set(ASKS)


@pytest.mark.parametrize("template", sorted(ASKS))
def test_the_page_carries_the_second_key(template: str) -> None:
    seen = _round(template)

    assert seen["tie"]["now"] is not None
    assert seen["tie"]["better"] == ROUND_TIE[template][1]
    assert seen["tie"]["label"] == ROUND_TIE[template][2]


@pytest.mark.parametrize("template", sorted(ASKS))
def test_a_level_score_with_a_better_second_key_is_a_record(template: str) -> None:
    """The defect: without this, the first maxed-out run is the last one
    that can ever say 自己ベスト更新."""

    plain = _round(template)
    here, tie = plain["score"], plain["tie"]["now"]
    worse = tie + 1000 if ROUND_TIE[template][1] == "less" else tie - 1

    beat = _round(
        template, {f"sidra.best.{template}": here, f"sidra.tie.{template}": worse}
    )

    assert beat["record"] is True


@pytest.mark.parametrize("template", sorted(ASKS))
def test_a_level_score_with_a_worse_second_key_is_not(template: str) -> None:
    plain = _round(template)
    here, tie = plain["score"], plain["tie"]["now"]
    finer = tie - 1000 if ROUND_TIE[template][1] == "less" else tie + 1

    held = _round(
        template, {f"sidra.best.{template}": here, f"sidra.tie.{template}": finer}
    )

    assert held["record"] is False


@pytest.mark.parametrize("template", sorted(ASKS))
def test_the_second_key_never_outranks_the_score(template: str) -> None:
    """It breaks ties. A worse round is still a worse round."""

    plain = _round(template)
    here, tie = plain["score"], plain["tie"]["now"]
    worse = tie + 1000 if ROUND_TIE[template][1] == "less" else tie - 1

    outranked = _round(
        template, {f"sidra.best.{template}": here + 1, f"sidra.tie.{template}": worse}
    )

    assert outranked["record"] is False
