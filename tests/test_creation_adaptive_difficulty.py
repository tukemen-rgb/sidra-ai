"""Three losses in a row, and the game steps toward you once.

§11 事実 2: a player who keeps failing leaves, and the difficulty dial is
no help to them because reaching for it means admitting to a setting.
§11 事実 3 is the warning attached: hidden dynamic difficulty makes
players distrust their own wins, and lets others farm it by losing.

So the assertions here are as much about restraint as about the help:
nothing moves before the third loss, the value it moves to is one the
author shipped, a win puts it back, a hand-set value is never touched,
and the page says which step it is on.

Two templates, because neither shows both halves: a masher can lose the
shooter and can win the race.
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

from sidra_ai.creation.adapt import (  # noqa: E402
    ADAPT_AFTER,
    ADAPT_PREAMBLE,
    PREAMBLE_NAMES,
)
from sidra_ai.creation.games import TEMPLATES, _DIFFICULTY, generate_game  # noqa: E402
from sidra_ai.creation.together import STORAGE_PREFIXES, probe_source  # noqa: E402
from sidra_ai.creation.tuning import SPEED_BINDING  # noqa: E402

LOSER, WINNER = "shooter", "racing"
LADDER = [pair[0] for pair in _DIFFICULTY[LOSER].values()]


def _run(template: str, request: str, stored: dict) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the rounds")
    found = re.search(
        r"<script>(.*?)</script>", generate_game(request, template=template).html, re.S
    )
    assert found is not None
    source = probe_source(
        found.group(1), speed_expr=SPEED_BINDING[template], frames=3800, stored=stored
    ).replace(
        "  writes: [...new Set(allWrites)].sort(),",
        "  writes: [...new Set(allWrites)].sort(), adapt: adaptFacts(),"
        f" streakAfter: allStored['sidra.streak.{template}']||null,"
        " said: (function(){const n=(function w(e){return [e].concat("
        "(e.children||[]).flatMap(w))})(allBody).filter(x=>x.id==='adapt')[0];"
        " return n?n.textContent:null})(),",
    )
    probe = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=300
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def _shooter(streak: int | None = None, **extra) -> dict:
    stored = {f"sidra.seen.{LOSER}": "1", **extra}
    if streak is not None:
        stored[f"sidra.streak.{LOSER}"] = str(streak)
    return _run(LOSER, "シューティングゲームを作って", stored)


# ------------------------------------------------------------- the restraint


@pytest.mark.parametrize("streak", [None, 1, ADAPT_AFTER - 1])
def test_nothing_moves_before_the_third_loss(streak) -> None:
    seen = _shooter(streak)

    assert seen["adapt"]["eased"] is False
    assert seen["atLoad"]["speed"] == _DIFFICULTY[LOSER]["normal"][0]


def test_a_hand_set_value_is_never_argued_with() -> None:
    """Reaching for the dial is a decision. This does not overrule one."""

    hardest = max(LADDER)
    seen = _shooter(ADAPT_AFTER, **{f"sidra.tune.{LOSER}": {"speed": hardest}})

    assert seen["adapt"]["manual"] is True
    assert seen["adapt"]["eased"] is False
    assert seen["atLoad"]["speed"] == hardest


# ------------------------------------------------------------------- the help


def test_three_losses_buy_exactly_one_step() -> None:
    """Toward the easy end of the author's ladder, and to a value on it.

    Not a percentage: "easier" is a direction along the three the author
    shipped, which is also why the catch template - whose axis is the
    interval between drops, where larger is gentler - needs no exception.
    """

    before = _shooter()["atLoad"]["speed"]
    after = _shooter(ADAPT_AFTER)["atLoad"]["speed"]

    assert after in LADDER
    assert LADDER.index(after) == max(0, LADDER.index(before) - 1)


def test_the_help_says_it_is_helping() -> None:
    """§11 事実 3: hidden help makes players distrust their own wins."""

    assert "やさしく" in _shooter(ADAPT_AFTER)["said"]
    assert "やさしく" not in _shooter()["said"]


def test_a_win_puts_it_back() -> None:
    """The help lasts exactly as long as the trouble.

    The pace is pinned by hand so this measures the streak and nothing
    else. Left to ease, the race would drop to a rung that cannot finish
    inside C-1104's clock and the "win" would be a buzzer - which is a
    defect in racing's ladder rather than in this rule, measured and filed
    as C-1404.
    """

    won = _run(
        WINNER,
        "レースゲームを作って",
        {
            f"sidra.seen.{WINNER}": "1",
            f"sidra.streak.{WINNER}": str(ADAPT_AFTER),
            f"sidra.tune.{WINNER}": {"speed": _DIFFICULTY[WINNER]["normal"][0]},
        },
    )

    assert won["atBreak"]["beats"] == 0, "the round meant to be won was lost"
    assert won["streakAfter"] == "0"


def test_a_loss_counts_up() -> None:
    seen = _shooter(1)

    assert seen["atBreak"]["beats"] > 0, "the round meant to be lost was won"
    assert seen["streakAfter"] == "2"


# ------------------------------------------------- what the page cannot say


def test_three_is_the_number_the_notes_give() -> None:
    assert ADAPT_AFTER == 3


def test_the_streak_never_leaves_the_machine() -> None:
    for banned in ("fetch(", "XMLHttpRequest", "://", "sendBeacon", "WebSocket"):
        assert banned not in ADAPT_PREAMBLE


def test_the_storage_key_is_declared() -> None:
    assert "sidra.streak." in STORAGE_PREFIXES


def test_the_speed_is_read_once_at_load() -> None:
    """Nothing may shift under a player mid-round, which is why the eased
    value applies from the next load rather than the next frame."""

    body = re.search(
        r"<script>(.*?)</script>", generate_game("ゲームを作って", template=LOSER).html, re.S
    ).group(1)

    # Call sites, not the definition: one, in the const the template reads
    # its speed from. A call per frame would let the value move mid-round.
    assert body.count("=adaptSpeed(") == 1
    assert "const FALL=adaptSpeed(" in body


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_no_template_shadows_an_adapt_name(template: str) -> None:
    body = TEMPLATES[template].script
    for name in PREAMBLE_NAMES:
        assert f"function {name}(" not in body
        assert f"const {name}=" not in body
        assert f"let {name}=" not in body
