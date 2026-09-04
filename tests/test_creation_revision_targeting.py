"""A revision finds the page it was talking about.

「猫のほうを難しくして」 can only mean the cat game. But 猫 is not a genre
word, so the message fell through to "whatever was made last" and quietly
adjusted the puzzle instead - the operator asked to change one thing and a
different thing changed, with nothing said.

Three rules, most specific first: the name, then the genre, then the
latest. The name is matched on its *distinctive* part - C-1125's rule
asked again - so two kinds of title are deliberately unaddressable:

* one the operator never chose (the template's own default), because a
  page nobody named should not answer to the name we gave it;
* one that is only its genre word, because 「パズル」 would otherwise
  swallow every message mentioning puzzles, and the genre rule handles
  those correctly anyway.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.intent import detect_creation_intent  # noqa: E402
from sidra_ai.creation.revise import (  # noqa: E402
    _distinctive_name,
    find_target_meta,
)
from sidra_ai.creation.router import build_default_router  # noqa: E402

#: Made in this order, so "latest" is the puzzle and every wrong answer is
#: the same wrong answer.
MADE = ("猫のゲームを作って", "ゲームを作って", "レースゲームを作って", "パズルゲームを作って")


@pytest.fixture(scope="module")
def made() -> str:
    directory = tempfile.mkdtemp(prefix="revision-target-")
    router = build_default_router(data_dir=directory)
    for request in MADE:
        router.route(request, detect_creation_intent(request), [])
        # Second-resolution stamps; without this the order is not the order.
        time.sleep(1.1)
    return directory


def _pick(directory: str, message: str) -> str | None:
    found = find_target_meta(directory, message)
    return found[1]["template"] if found else None


@pytest.mark.parametrize(
    "message,want",
    [
        # By name, where no genre word appears at all: the defect itself.
        ("猫のほうを難しくして", "fishing"),
        ("猫のゲームをやさしくして", "fishing"),
        # By genre, still.
        ("レースのほうを難しくして", "racing"),
        ("パズルを難しくして", "puzzle"),
        # Nothing named: the latest, which is what a bare ask means.
        ("難しくして", "puzzle"),
        ("もっとやさしく", "puzzle"),
    ],
)
def test_the_revision_lands_on_the_page_that_was_meant(
    made: str, message: str, want: str
) -> None:
    assert _pick(made, message) == want


def test_a_page_nobody_named_is_not_addressable_by_name() -> None:
    """The default 「タイミング釣り」 yielded 「タイミング」 as a distinctive
    name, so a message containing that word picked a page nobody had
    called anything."""

    assert not _distinctive_name(
        {"title": "タイミング釣り", "template": "fishing", "request": "ゲームを作って"}
    )


def test_a_title_that_is_only_its_genre_is_not_addressable_by_name() -> None:
    assert not _distinctive_name(
        {"title": "パズル", "template": "puzzle", "request": "パズルゲームを作って"}
    )


def test_a_named_page_is() -> None:
    assert _distinctive_name(
        {"title": "猫", "template": "fishing", "request": "猫のゲームを作って"}
    ) == "猫"
