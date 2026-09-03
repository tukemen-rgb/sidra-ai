"""Today's board is the same board for everyone, and nobody asked anyone.

§8 事実 4・7: what brings people back is a shared attempt - the same
layout, the same day. The obvious way to build one is a server handing out
a puzzle, and that way is closed here: the artifact is a file that talks to
nothing.

A date is already shared. Every device knows what day it is, so a seed
derived from the date is a seed everyone derives identically, and the
coordination costs nothing. The page hashes ``YYYY-MM-DD``; that is the
whole mechanism.

The three comparisons that make the claim are all made against the running
page: two different requests on the same day get the same world, the next
day is a different one, and with the switch off each request keeps its own
world. The last one matters most - a daily seed that applied by default
would have quietly replaced the thing that makes a generated game *that
person's* game, and C-1112's revisions rebuild expecting the same world.
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

from sidra_ai.creation.daily import (  # noqa: E402
    DAILY_PREAMBLE,
    PREAMBLE_NAMES,
    probe_source,
)
from sidra_ai.creation.games import TEMPLATES, generate_game  # noqa: E402
from sidra_ai.creation.round import probe_source as round_probe  # noqa: E402
from sidra_ai.creation.together import probe_source as together_probe  # noqa: E402
from sidra_ai.creation.tuning import SPEED_BINDING, panel_schema  # noqa: E402

#: A template whose world a seed decides, and the most visible of them: the
#: adventure lays out three rooms from it.
BOARD = "adventure"
REQUESTS = ("迷宮を冒険するゲームを作って", "べつの冒険ゲームを作って")


def _seeds(*, on: bool, stamp: str) -> list[dict]:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to read the page's own seed")
    out = []
    for request in REQUESTS:
        page = generate_game(request, template=BOARD).html
        script = re.search(r"<script>(.*?)</script>", page, re.S)
        assert script is not None
        probe = subprocess.run(
            ["node", "-"],
            input=round_probe(
                script.group(1),
                stamp=stamp,
                stored={f"sidra.tune.{BOARD}": {"daily": on}},
            ),
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert probe.returncode == 0, probe.stderr[:400]
        out.append(json.loads(probe.stdout.strip().splitlines()[-1]))
    return out


def _preamble(*, on: bool, stamp: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to run the daily preamble")
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(stamp=stamp, on=on),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


#: Every template, and the board rather than the seed. C-1107 measured one
#: template and compared seed values; C-1118 found what that missed, and
#: C-1119 closed it - so the check is now what a player would see.
def _board(template: str, request: str, *, on: bool, stamp: str, pin: int) -> int:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to draw the board")
    page = generate_game(request, template=template).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=together_probe(
            script.group(1),
            speed_expr=SPEED_BINDING[template],
            frames=120,
            quiet=True,
            # Particles draw with Math.random and fire on their own in half
            # the templates; C-1020 guarantees reduced motion is what drops
            # them, which is what makes the board observable at all.
            reduced=True,
            random_pin=pin,
            stamp=stamp,
            stored={
                f"sidra.tune.{template}": {"daily": on},
                f"sidra.seen.{template}": "1",
            },
        ),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])["geometry"]


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_every_template_draws_the_same_board_today(template: str) -> None:
    """Two requests, two different Math.random streams, one day.

    The two streams are the point: a board that comes from chance rather
    than from the seed draws differently, which is exactly what catch did
    until C-1119 and what the seed comparison could never see.
    """

    a = _board(template, REQUESTS[0], on=True, stamp="2026-09-03", pin=111)
    b = _board(template, REQUESTS[1], on=True, stamp="2026-09-03", pin=222)

    assert a == b


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_every_template_draws_a_different_board_tomorrow(template: str) -> None:
    today = _board(template, REQUESTS[0], on=True, stamp="2026-09-03", pin=111)
    tomorrow = _board(template, REQUESTS[0], on=True, stamp="2026-09-04", pin=111)

    assert today != tomorrow


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_with_the_switch_off_every_template_keeps_its_own(template: str) -> None:
    a = _board(template, REQUESTS[0], on=False, stamp="2026-09-03", pin=111)
    b = _board(template, REQUESTS[1], on=False, stamp="2026-09-03", pin=222)
    shared = _board(template, REQUESTS[0], on=True, stamp="2026-09-03", pin=111)

    assert a != b
    assert a != shared


# ------------------------------------------------------------ the three claims


def test_two_requests_get_the_same_board_today() -> None:
    a, b = _seeds(on=True, stamp="2026-09-03")

    assert a["seed"] is not None
    assert a["seed"] == b["seed"]


def test_tomorrow_is_a_different_board() -> None:
    today, _ = _seeds(on=True, stamp="2026-09-03")
    tomorrow, _ = _seeds(on=True, stamp="2026-09-04")

    assert today["seed"] != tomorrow["seed"]


def test_with_the_switch_off_a_request_keeps_its_own_world() -> None:
    """The default has to stay the request-derived seed.

    A daily seed that applied by default would replace the thing that makes
    a generated game that person's game, and a revision rebuilt from the
    same request would come back to a different world.
    """

    a, b = _seeds(on=False, stamp="2026-09-03")
    shared, _ = _seeds(on=True, stamp="2026-09-03")

    assert a["seed"] != b["seed"]
    assert a["seed"] != shared["seed"]


# ------------------------------------------------------------- the mechanism


def test_the_same_day_hashes_the_same_twice() -> None:
    first = _preamble(on=True, stamp="2026-09-03")
    second = _preamble(on=True, stamp="2026-09-03")

    assert first["stamp"] == "2026-09-03"
    assert first["seed"] == second["seed"] == first["daily"]


def test_the_switch_off_returns_the_fallback_untouched() -> None:
    off = _preamble(on=False, stamp="2026-09-03")

    assert off["seed"] == off["fallback"]
    # Still computable - the switch decides whether it is used, not whether
    # the page can work it out.
    assert off["daily"] != off["fallback"]


def test_nothing_is_fetched_to_share_a_board() -> None:
    """The whole reason the date was the answer."""

    for banned in ("fetch(", "XMLHttpRequest", "://", "sendBeacon", "WebSocket"):
        assert banned not in DAILY_PREAMBLE


# ------------------------------------------------- the switch and the label


def test_the_panel_carries_the_switch_off_by_default() -> None:
    from sidra_ai.creation.games import _DIFFICULTY

    fields = {
        f["key"]: f
        for f in panel_schema(
            BOARD, _DIFFICULTY[BOARD], difficulty="normal", accent="#000000"
        )["fields"]
    }

    assert fields["daily"]["type"] == "flag"
    assert fields["daily"]["default"] is False


def test_the_result_says_whose_board_it_was() -> None:
    on, _ = _seeds(on=True, stamp="2026-09-03")

    said = [line for line in on["strip"] if "今日の挑戦" in line]
    assert said, on["strip"]
    assert "2026-09-03" in said[0]


def test_the_result_stays_quiet_when_the_switch_is_off() -> None:
    """A line that always said 今日の挑戦 would make the claim meaningless."""

    off, _ = _seeds(on=False, stamp="2026-09-03")

    assert not [line for line in off["strip"] if "今日の挑戦" in line]


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_no_template_shadows_the_daily_names(template: str) -> None:
    body = TEMPLATES[template].script
    for name in PREAMBLE_NAMES:
        assert f"function {name}(" not in body
        assert f"const {name}=" not in body
        assert f"let {name}=" not in body
