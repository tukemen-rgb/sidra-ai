"""「もう見た」は文面についての判断であって、型についてではない (C-1738).

§8 事実 8 asks that a page be playable the moment it opens, and C-1111's
answer is that the briefing - objective, controls, threat - is shown on
the first visit and skipped afterwards, because three lines somebody has
read are not news.

What nobody had checked is what "afterwards" was about. The mark is
``sidra.seen.<template>`` and its value was the single character ``'1'``:
*this template has been opened*. That is the same claim as *these three
lines have been read* only while every game a template makes says the
same three lines.

Racing's does not. Its 目標 line carries the lap count from the
difficulty table, so 「コースに沿って 2 周を走り切り」 (easy), 3 周
(normal) and 4 周 (hard) are
different news under one mark, and the second game dropped the player
straight into play with its goal never stated. ``together.py``'s own
``DEVICE_WIDE`` note - "the three lines belong to the template" - was
written by this loop two cycles ago and was wrong; it is corrected with
this item.

Both directions. Showing the briefing every time passes the first check
on its own, and that is the defect C-1111 removed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.together import DEVICE_WIDE, probe_source
from sidra_ai.creation.tuning import SPEED_BINDING

TEMPLATE = "racing"


def _page(template: str, difficulty: str) -> tuple[str, str]:
    html = generate_game("ゲームを作って", template=template, difficulty=difficulty).html
    found = re.search(r"<script>(.*?)</script>", html, re.S)
    assert found is not None
    said = re.search(r"GBRIEF=(\[.*?\]);", found.group(1), re.S)
    return found.group(1), (said.group(1) if said else "")


def _open(template: str, script: str, stored: dict) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to open the page")
    source = probe_source(
        script, speed_expr=SPEED_BINDING[template], frames=120, stored=stored
    ).replace(
        "  writes: [...new Set(allWrites)].sort(),",
        "  writes: [...new Set(allWrites)].sort(),"
        f" seenStored: allStored['sidra.seen.{template}']||null,",
    )
    probe = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=180
    )
    assert probe.returncode == 0, probe.stderr[:400]
    out = json.loads(probe.stdout.strip().splitlines()[-1])
    return {**out["atLoad"]["gate"], "seenStored": out.get("seenStored")}


def _gate(template: str, script: str, stored: dict) -> dict:
    return _open(template, script, stored)


@pytest.fixture(scope="module")
def racing() -> dict:
    here, here_said = _page(TEMPLATE, "normal")
    other, other_said = _page(TEMPLATE, "hard")
    fresh = _gate(TEMPLATE, here, {})
    return {
        "here": here,
        "other": other,
        "saidHere": here_said,
        "saidOther": other_said,
        "fresh": fresh,
        "mark": fresh["brief"],
    }


def test_the_two_racing_games_really_say_different_things(racing: dict) -> None:
    """Or everything below is testing nothing."""

    assert racing["saidHere"] != racing["saidOther"]
    assert "3 周" in racing["saidHere"] and "4 周" in racing["saidOther"]


def test_a_first_visit_is_never_skipped(racing: dict) -> None:
    assert racing["fresh"]["state"] == "title"
    assert racing["fresh"]["skipped"] is False
    assert racing["fresh"]["seen"] is False


def test_the_same_words_are_not_news_twice(racing: dict) -> None:
    """C-1111's own contract, unchanged."""

    gate = _gate(TEMPLATE, racing["here"], {f"sidra.seen.{TEMPLATE}": racing["mark"]})
    assert gate["skipped"] is True
    assert gate["state"] == "playing"


def test_different_words_are_news_again(racing: dict) -> None:
    """The defect: a goal the player has never been told."""

    gate = _gate(TEMPLATE, racing["other"], {f"sidra.seen.{TEMPLATE}": racing["mark"]})
    assert gate["skipped"] is False, "文面が変わったのに「もう見た」で飛ばした"
    assert gate["state"] == "title"


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_the_page_writes_down_which_words_it_showed(template: str) -> None:
    """Read off the store, because the read side cannot see this.

    ``gateSeen`` adopts a bare ``'1'``, so a page that kept writing
    ``'1'`` would have its own next visit accept it and nothing above
    would notice - the destruction battery walked straight through the
    read-side version of this check.
    """

    here, _ = _page(template, "normal")
    opened = _open(template, here, {})
    assert opened["seenStored"], f"{template}: 既読を書いていない"
    assert opened["seenStored"] != "1", f"{template}: 何の文面かを書いていない"
    assert opened["seenStored"] == opened["brief"], (
        template,
        opened["seenStored"],
        opened["brief"],
    )


def test_what_an_older_page_wrote_is_honoured_once(racing: dict) -> None:
    """``'1'`` is somebody who read the lines they were shown.

    Refusing it would make every existing player read a briefing again -
    the thing C-1111 removed - for a change that is about the words.
    """

    gate = _gate(TEMPLATE, racing["here"], {f"sidra.seen.{TEMPLATE}": "1"})
    assert gate["skipped"] is True


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_every_template_remembers_the_words_it_showed(template: str) -> None:
    here, here_said = _page(template, "normal")
    other, other_said = _page(template, "hard")
    fresh = _gate(template, here, {})
    assert fresh["skipped"] is False, template
    mark = fresh["brief"]
    assert mark, template
    assert _gate(template, here, {f"sidra.seen.{template}": mark})["skipped"] is True
    assert _gate(template, here, {f"sidra.seen.{template}": "1"})["skipped"] is True
    # Only where the words actually differ: nine of ten say the same three
    # lines at every difficulty, and asking "it changes when it changes"
    # of a page whose words never change would make this check a lie.
    skipped = _gate(template, other, {f"sidra.seen.{template}": mark})["skipped"]
    assert skipped is (here_said == other_said), (template, here_said == other_said)


def test_the_reason_in_the_registry_says_what_is_remembered() -> None:
    """The note this loop wrote in C-1734 was wrong; it is corrected here."""

    why = DEVICE_WIDE["sidra.seen."]
    assert "C-1738" in why
    assert "型を開いたか" in why, why
