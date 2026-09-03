"""One line a person can paste, that gives nothing away.

§8 事実 7. What spreads a game is a result its player wants to show;
what makes showing it safe for everybody else is that the result cannot
be read backwards into the answer.

Everything about *what gets copied* is read off the running page: the
round is played out, the result comes up, the page's own button is
pressed, and the string that reached the clipboard is what gets checked.
A page containing the word ``clipboard`` and a page that copies a
spoiler-free line are different facts, and only the second is worth
asserting.

Three absences carry the item, and each is a rule rather than an
oversight: no URL, nothing about the person (their words, their title,
their device), and nothing about the board - above all not the
request-derived seed. The daily stamp is the exception that proves it:
it is safe precisely because it is everybody's.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.games import TEMPLATES, generate_game  # noqa: E402
from sidra_ai.creation.share import (  # noqa: E402
    BANNED_IN_TEXT,
    PREAMBLE_NAMES,
    SHARE_EMOJI,
    SHARE_MAX,
    SHARE_NAME,
    SHARE_PREAMBLE,
    SHARE_TYPICAL,
    leaks,
    probe_source,
    share_spec,
)

KEYS = sorted(TEMPLATES)
REQUEST = "ゲームを作って"
STAMP = "2026-09-03"
SEED = zlib.crc32(REQUEST.encode("utf-8"))
#: One template is played end to end in both states; the metric does all
#: nine, twice each.
PLAYED = "fishing"


def _play(template: str, *, daily: bool = False) -> tuple[dict, str]:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to press the page's own button")
    art = generate_game(REQUEST, template=template)
    script = re.search(r"<script>(.*?)</script>", art.html, re.S)
    assert script is not None
    stored = {f"sidra.tune.{template}": {"daily": True}} if daily else {}
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(script.group(1), stored=stored, stamp=STAMP),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1]), art.title


# ----------------------------------------------------- what reaches the clipboard


def test_pressing_the_button_copies_the_line() -> None:
    seen, _ = _play(PLAYED)

    assert seen["button"] is True
    assert seen["afterClick"] == [seen["facts"]["text"]]
    assert seen["facts"]["text"]


def test_the_keyboard_is_the_same_act_by_another_route() -> None:
    seen, _ = _play(PLAYED)

    assert seen["facts"]["copies"] == 2


def test_there_is_nothing_to_copy_before_a_round_ends() -> None:
    """A button that answered mid-round would be sharing a number nobody
    finished scoring."""

    seen, _ = _play(PLAYED)

    assert seen["early"]["ready"] is False
    assert seen["early"]["text"] is None


@pytest.mark.parametrize("template", KEYS)
def test_the_copied_line_gives_nothing_away(template: str) -> None:
    seen, title = _play(template)
    copied = seen["afterClick"][0]

    assert leaks(copied, request=REQUEST, title=title, seed=SEED) == []


@pytest.mark.parametrize("template", KEYS)
def test_the_line_carries_the_score_and_a_row_derived_from_it(template: str) -> None:
    """A fixed row would be decoration; this one has to mean something."""

    seen, _ = _play(template)
    facts = seen["facts"]
    score = facts["score"]
    want = (
        ""
        if not (score and score > 0)
        else facts["emoji"] * max(1, min(SHARE_MAX, round(score / facts["per"])))
    )

    assert str(score) in facts["text"]
    assert facts["bar"] == want
    if want:
        assert want in facts["text"]


def test_today_is_named_only_when_the_board_is_shared() -> None:
    """The stamp is safe to paste because it is everybody's. Saying it over
    a board nobody else has would make the claim meaningless."""

    shared, _ = _play(PLAYED, daily=True)
    private, _ = _play(PLAYED, daily=False)

    assert STAMP in shared["facts"]["text"]
    assert STAMP not in private["facts"]["text"]


def test_the_row_never_grows_past_its_bound() -> None:
    """A several-hundred-point round would otherwise paste as several
    hundred characters."""

    seen, _ = _play("puzzle")
    facts = seen["facts"]

    assert len(facts["bar"]) <= SHARE_MAX * len(facts["emoji"])


# ------------------------------------------------- what the page cannot say


def test_a_line_with_a_link_in_it_would_be_caught() -> None:
    """The detector itself, since every other assertion leans on it."""

    for banned in BANNED_IN_TEXT:
        assert leaks(f"釣り 🐟 釣果 3 {banned}", request="x", title="", seed=0)


def test_the_detector_reads_the_seed_and_the_persons_words() -> None:
    assert leaks(f"釣り {SEED}", request=REQUEST, title="", seed=SEED)
    assert leaks("釣り 迷宮の冒険", request="x", title="迷宮の冒険", seed=0)
    assert leaks("釣り ドラゴン", request="ドラゴン のゲーム", title="", seed=0)
    assert leaks("釣り 🐟 釣果 3", request=REQUEST, title="迷宮の冒険", seed=SEED) == []


@pytest.mark.parametrize("template", KEYS)
def test_every_template_names_itself_without_naming_the_person(template: str) -> None:
    spec = share_spec(template)

    assert spec["name"] == SHARE_NAME[template]
    assert spec["emoji"] == SHARE_EMOJI[template]
    assert spec["per"] >= 1
    assert spec["max"] == SHARE_MAX


def test_a_typical_round_fills_about_half_the_row() -> None:
    """Never all-or-nothing: a good round has to read as better than usual."""

    assert 1 < SHARE_TYPICAL < SHARE_MAX


def test_the_line_goes_nowhere_by_itself() -> None:
    for banned in ("fetch(", "XMLHttpRequest", "://", "sendBeacon", "WebSocket", "share("):
        assert banned not in SHARE_PREAMBLE


@pytest.mark.parametrize("template", KEYS)
def test_no_template_shadows_a_share_name(template: str) -> None:
    body = TEMPLATES[template].script
    for name in PREAMBLE_NAMES:
        assert f"function {name}(" not in body
        assert f"const {name}=" not in body
        assert f"let {name}=" not in body
