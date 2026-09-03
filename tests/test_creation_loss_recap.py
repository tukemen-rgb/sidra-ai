"""The result strip says, in one line, why this go ended.

A losing round used to offer 「R / タップでもう一度」 and nothing else: it
asked for another attempt without saying what would make the next one
different. The line is built only from counters the round already keeps,
so the tests are mostly about restraint - a win is never explained, a
cause counted zero is never named, and a verdict is never settled while
the go is still being played.

Driven, not grepped: each wired template is made to actually lose, and the
number in the line is checked against raw page state rather than against
the table the line was built from.
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

from sidra_ai.creation.games import TEMPLATES, _DIFFICULTY, generate_game  # noqa: E402
from sidra_ai.creation.recap import (  # noqa: E402
    LOSS_UNWIRED,
    LOSS_WIRED,
    PREAMBLE_NAMES,
    probe_source,
)

#: One request per wired template, and how to make that template lose.
ASKS: dict[str, tuple[str, dict]] = {
    "shooter": ("シューティングゲームを作って", {}),
    "marble": ("3D のゲームを作って", {}),
    # Untouched it never falls, so its one cause is zero: hold right and it
    # walks off the ledges.
    "platformer": ("ジャンプアクションを作って", {"hold": "ArrowRight"}),
    "kaiju": ("怪獣と戦うゲームを作って", {}),
    # Since C-1404 every racing rung finishes untouched, so the loss comes
    # from the panel's slowest pace - the way C-1105 makes one.
    "racing": (
        "レースゲームを作って",
        {"stored": {"speed": min(p[0] for p in _DIFFICULTY["racing"].values())}},
    ),
}


def _play(template: str, **override) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the rounds")
    request, drive = ASKS[template]
    found = re.search(r"<script>(.*?)</script>", generate_game(request).html, re.S)
    assert found is not None
    run = subprocess.run(
        ["node", "-"],
        input=probe_source(found.group(1), template=template, **{**drive, **override}),
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert run.returncode == 0, run.stderr.strip()[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


# ------------------------------------------------------------ the bookkeeping


def test_every_template_is_either_wired_or_has_a_reason() -> None:
    assert set(LOSS_WIRED) | set(LOSS_UNWIRED) == set(TEMPLATES)
    assert not set(LOSS_WIRED) & set(LOSS_UNWIRED)
    assert all(reason.strip() for reason in LOSS_UNWIRED.values())


def test_an_unwired_template_carries_the_names_and_says_nothing() -> None:
    """The functions exist everywhere so the strip never has to ask."""

    page = generate_game("キャッチゲームを作って").html
    for name in PREAMBLE_NAMES:
        assert name in page


# ------------------------------------------------------------------- the line


@pytest.mark.parametrize("template", sorted(LOSS_WIRED))
def test_a_loss_is_explained_with_a_number(template: str) -> None:
    seen = _play(template)

    assert seen["atEnd"]["lost"], "the go that was produced was not a loss"
    line = seen["atEnd"]["line"]
    assert line, "a loss with a counted cause said nothing"
    assert any(ch.isdigit() for ch in line), line


@pytest.mark.parametrize("template", sorted(LOSS_WIRED))
def test_the_line_reaches_the_result_strip(template: str) -> None:
    seen = _play(template)

    assert seen["atEnd"]["line"] in seen["strip"]


@pytest.mark.parametrize("template", sorted(LOSS_WIRED))
def test_a_win_is_never_explained(template: str) -> None:
    """Second-guessing somebody who has just succeeded."""

    won = _play(template)["afterWin"]

    assert isinstance(won, dict), won
    assert not won["lost"]
    assert won["line"] == ""


@pytest.mark.parametrize("template", sorted(LOSS_WIRED))
def test_no_verdict_is_settled_while_the_go_is_still_live(template: str) -> None:
    """Two of the wired conditions are "did not reach the winning state",
    which is true from the first frame. The round-over guard is what stops
    the page holding a verdict about a round still being played."""

    assert _play(template)["verdictWhileLive"] is False


@pytest.mark.parametrize(
    "template,expected",
    [
        ("shooter", lambda raw: 3 - raw["hp"]),
        ("platformer", lambda raw: raw["respawns"]),
        ("kaiju", lambda raw: 3 - raw["cycles"]),
    ],
)
def test_the_count_is_the_counters_not_a_constant(template: str, expected) -> None:
    """Checked against raw page state rather than the table the line was
    built from, so a number that was invented disagrees with it."""

    seen = _play(template)
    raw = seen["counters"]

    assert str(int(expected(raw))) in seen["atEnd"]["line"]


def test_a_cause_counted_zero_is_never_named() -> None:
    """「落下 0 回」 on a result strip is worse than saying nothing."""

    quiet = _play("platformer", hold=None)["atEnd"]

    assert quiet["lost"], "the untouched round was not a loss"
    assert quiet["line"] == ""
