"""C-1768: 「今日の」 means everybody got this board, so say when they didn't.

§8 事実 7 records why Wordle's sharing worked - a spoiler-free boast about
a challenge everybody got - and this product copies both halves. The line
wrote 「今日の」 on the strength of the seed alone, and the seed is only
half of the board: the panel holds the other half. One seed and one date,
with the band swung across the author's own span, gave catch 15 against
40, fishing 49 against 122, puzzle 10 columns against 14 - all pasting the
same date.

Said rather than taken away: forcing the ladder back for a daily run would
silently undo a control the player used (C-1729, C-1764). Which is why the
untouched case is here too - "always append a caveat" would satisfy every
moved board and make the note worthless on the days it matters.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.games import _DIFFICULTY, generate_game  # noqa: E402
from sidra_ai.creation.share import leaks, probe_source  # noqa: E402
from sidra_ai.creation.tuning import AXIS_LABELS  # noqa: E402

STAMP = "2026-09-03"
REQUEST = "ゲームを作って"
TEMPLATES = ("puzzle", "fishing", "catch")


def _line(template: str, store: dict) -> str:
    html = generate_game(REQUEST, template=template).html
    body = re.search(r"<script>(.*?)</script>", html, re.S)
    assert body is not None
    out = subprocess.run(
        ["node", "-"],
        input=probe_source(body.group(1), stored={f"sidra.tune.{template}": store}),
        capture_output=True, text=True, timeout=180,
    )
    assert out.returncode == 0, out.stderr[-400:]
    seen = json.loads(out.stdout.strip().splitlines()[-1])
    copied = seen.get("clipboard") or []
    assert copied, "the page copied nothing"
    return copied[0]


def _moved_band(template: str) -> float:
    rungs = _DIFFICULTY[template]
    default = rungs["normal"][1]
    return max((p[1] for p in rungs.values()), key=lambda v: abs(v - default))


# ------------------------------------------------------------ it says so


@pytest.mark.parametrize("template", TEMPLATES)
def test_a_moved_board_is_named_in_the_daily_line(template: str) -> None:
    band = _moved_band(template)
    text = _line(template, {"daily": True, "band": band})

    assert STAMP in text, "a tuned daily board lost its date"
    assert AXIS_LABELS[template][1] in text, text
    assert f"{band:g}" in text, text


@pytest.mark.parametrize("template", TEMPLATES)
def test_both_axes_are_named_when_a_preset_moved_both(template: str) -> None:
    """Picking a rung in the panel writes speed and band, so the axes say
    what moved - the rung itself is deliberately not named."""

    speed, band = _DIFFICULTY[template]["hard"]
    text = _line(
        template,
        {"daily": True, "difficulty": "hard", "speed": speed, "band": band},
    )
    labels = AXIS_LABELS[template]

    assert labels[0] in text and labels[1] in text, text
    assert "難度" not in text, text


# --------------------------------------------------------- and only then


@pytest.mark.parametrize("template", TEMPLATES)
def test_an_untouched_daily_board_carries_no_caveat(template: str) -> None:
    text = _line(template, {"daily": True})

    assert STAMP in text
    assert "（" not in text, f"a board everybody got was caveated anyway: {text}"


@pytest.mark.parametrize("template", TEMPLATES)
def test_a_dial_put_back_where_it_started_is_not_a_change(template: str) -> None:
    text = _line(template, {"daily": True, "band": _DIFFICULTY[template]["normal"][1]})

    assert "（" not in text, text


@pytest.mark.parametrize("template", TEMPLATES)
def test_a_stored_rung_that_moved_no_axis_is_not_a_change(template: str) -> None:
    """Naming the rung would have claimed a changed board for a board that
    had not changed - the same overclaim, in the other direction."""

    text = _line(template, {"daily": True, "difficulty": "hard"})

    assert "（" not in text, text


@pytest.mark.parametrize("template", TEMPLATES)
def test_a_private_board_is_still_not_dated(template: str) -> None:
    """C-1118's sentinel, in the same run."""

    text = _line(template, {"band": _moved_band(template)})

    assert STAMP not in text, text
    assert "今日の" not in text, text


# ------------------------------------------------------- and leaks nothing


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_caveat_leaks_nothing(template: str) -> None:
    """Labels are the product's own words and numbers come from the
    author's span, so nothing new reaches the clipboard."""

    text = _line(template, {"daily": True, "band": _moved_band(template)})

    assert leaks(text, request=REQUEST, title="", seed=164438993) == []
