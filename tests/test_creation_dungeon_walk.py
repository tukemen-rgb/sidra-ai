"""The dungeon is walked to its own win, with no flag set by hand (§3, C-1675).

§3's skeleton is a mission graph: a lock stops progress, a key opens it,
and the dependencies say which must come first. The adventure implements
one - clear the roamers, the key falls, pick it up, cross to the altar,
fell the guardian, open the chest - and until now nothing walked it.

``creation_adventure_playable`` counts rooms and tiles in the generated
page and runs no frames. The only driver that reached ``state='win'`` was
``GUARD_PROBE``, which writes ``hero.key = true`` and steps into room 2:
that proves the chest opens for its key and nothing about the key being
got.

The source has also carried an unmeasured promise since C-1021 - ``The
optional door (§3): the run is winnable without ever opening it`` - and
an optional reward that turns out to be required is not a soft lock at
all, it is a hard one wearing the wrong name.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.adventure import run_probe
from sidra_ai.creation.games import generate_game


@pytest.fixture(scope="module")
def walk() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to walk the dungeon")
    page = generate_game("迷宮を冒険するゲームを作って").html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None, "the page carries no script"
    got = subprocess.run(
        ["node", "-"],
        input=run_probe(found.group(1)),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert got.returncode == 0, got.stderr[:400]
    return json.loads(got.stdout.strip().splitlines()[-1])


def test_the_run_reaches_its_win(walk: dict) -> None:
    won = walk["walked"]
    assert won["cleared"], "the roamers did not fall to the sword"
    assert won["held"], "the fallen key could not be picked up"
    assert won["fell"], f"the guardian still stood after {won['turns']} turns"
    assert won["state"] == "win", won["state"]


def test_the_optional_branch_is_optional(walk: dict) -> None:
    """The promise C-1021 wrote in a comment, turned into a measurement."""

    won = walk["walked"]
    assert won["state"] == "win", "nothing to say about a run that did not win"
    assert won["doorStands"], "the winning run opened the optional door"
    assert won["rewardStands"], "the winning run took the optional reward"
    assert not won["charm"], "the winning run carried the charm"
    assert won["gems"] == 0, f"the winning run spent {won['gems']} gems"
    assert won["hearts"] == 3, "the winning run bought hearts at the shrine"


def test_the_chest_needs_the_key_that_fell(walk: dict) -> None:
    """The same walk, with the key left lying where it dropped."""

    left = walk["leftBehind"]
    assert not left["held"], "the run that must not take the key took it"
    assert left["dropped"], "no key ever fell, so nothing was refused"
    assert left["fell"], "the guardian must fall in this run too"
    assert left["state"] != "win", "the chest opened with no key"


def test_the_chest_refuses_while_the_guardian_stands(walk: dict) -> None:
    for label in ("walked", "leftBehind"):
        assert walk[label]["guarded"] != "win", label


def test_the_key_waits_for_the_last_roamer(walk: dict) -> None:
    """A key that fell early would make the lock a decoration."""

    countdown = walk["walked"]["countdown"]
    assert len(countdown) >= 2, "only one roamer stood between key and hero"
    for step in countdown[:-1]:
        assert step["left"] > 0
        assert not step["drop"], f"the key fell with {step['left']} still standing"
    assert countdown[-1]["left"] == 0
    assert countdown[-1]["drop"], "the last roamer fell and no key came"


def test_the_walk_sets_no_flags(walk: dict) -> None:
    """The probe's own contract: what makes this measurement worth more
    than GUARD_PROBE's is that nothing is granted. If a later edit reached
    for ``hero.key = true`` the run would prove nothing again."""

    from sidra_ai.creation.adventure import RUN_PROBE

    for granted in ("hero.key = true", "hero.key=true", "hero.charm = true"):
        assert granted not in RUN_PROBE, granted
