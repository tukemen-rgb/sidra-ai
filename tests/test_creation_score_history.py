"""C-1432: the last few runs, in the order they happened.

A best is one number and it only moves upward, so a page that keeps nothing
else can say 「自己ベスト 24（あと 5）」 all afternoon without ever telling a
player they are getting closer. The row is what shows a day's progress on
the days the record does not move.

Restarting is a real ``location.reload()``, so rounds cannot share a page:
each load below is its own process, and what carries between them is
exactly what carries in a browser - the store.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.round import history_probe_source

ASK = "キャッチゲームを作って"

#: Six played loads against a cap of five, with one untouched load in the
#: middle. The holds differ so the scores do, which is what stops a page
#: printing one constant from satisfying everything here.
HOLDS = (
    "ArrowRight", "ArrowLeft", None, "ArrowRight",
    "ArrowLeft", "ArrowRight", "ArrowLeft",
)


@pytest.fixture(scope="module")
def loads():
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the rounds")
    found = re.search(r"<script>(.*?)</script>", generate_game(ASK).html, re.S)
    assert found is not None
    out, store = [], {}
    for hold in HOLDS:
        run = subprocess.run(
            ["node", "-"],
            input=history_probe_source(found.group(1), store=store, hold=hold, step=25),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert run.returncode == 0, run.stderr[:400]
        seen = json.loads(run.stdout.strip().splitlines()[-1])
        store = seen["store"]
        out.append({"hold": hold, **seen})
    return out


def test_the_rounds_actually_differ(loads) -> None:
    """Otherwise a page printing one constant passes everything below."""

    scores = {r["score"] for r in loads if r["hold"] is not None}
    assert len(scores) > 1, scores


def test_each_played_round_appends_its_own_score(loads) -> None:
    cap = loads[0]["max"]
    wanted: list[int] = []
    for turn, r in enumerate(loads):
        if r["hold"] is not None:
            wanted.append(r["score"])
            wanted = wanted[-cap:]
        assert r["runs"] == wanted, f"load {turn}"


def test_a_round_nobody_played_stays_out(loads) -> None:
    idle = [r for r in loads if r["hold"] is None]
    assert idle, "no untouched load was driven"
    for r in idle:
        assert r["touched"] is False
        assert r["runs"] == r["before"]


def test_the_row_survives_the_reload(loads) -> None:
    assert loads[1]["before"], "the second load started from an empty row"


def test_a_worse_run_is_not_quietly_dropped(loads) -> None:
    """A row that hid its bad days would be flattery, and nobody could use
    it to tell whether they are improving."""

    last = loads[-1]["runs"]
    assert len(last) > 1
    assert last != sorted(last), last


def test_the_row_reaches_the_result_strip(loads) -> None:
    shown = [r for r in loads if r["said"]]
    assert shown, "the row was never drawn"
    latest = shown[-1]
    want = "直近 " + " / ".join(str(v) for v in latest["runs"])
    assert want in latest["said"]


def test_the_cap_holds_and_is_reached(loads) -> None:
    cap = loads[0]["max"]
    played = [r for r in loads if r["hold"] is not None]
    assert len(played) > cap, "the cap was never reached"
    assert len(loads[-1]["runs"]) == cap
