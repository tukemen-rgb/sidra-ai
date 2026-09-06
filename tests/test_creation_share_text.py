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
    bar_for,
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
    # By the page's rule (C-1437). Python's own `round` sends a half to
    # the even side while the page's `Math.round` sends it up, so this
    # test used to fail a correct page whenever score/per landed exactly
    # halfway - which any change to a template's points can cause.
    want = bar_for(score, share_spec(template))

    assert str(score) in facts["text"]
    assert facts["bar"] == want
    if want:
        assert want in facts["text"]


def test_today_is_named_only_when_the_board_is_shared() -> None:
    """The stamp is safe to paste because it is everybody's. Saying it over
    a board nobody else has would make the claim meaningless.

    Driven on a template whose board actually comes from the seed. This
    test used to run on ``fishing`` and passed, which was the bug: fishing
    lays its board out with ``Math.random`` and has no seed at all, so it
    was dating a board only that player had. C-1118's sweep found it - see
    ``tests/test_creation_features_together.py`` for the other half.
    """

    seeded = "adventure"
    shared, _ = _play(seeded, daily=True)
    private, _ = _play(seeded, daily=False)

    assert shared["round"]["seed"] is not None
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


# --- the mirror, held to the page it mirrors (C-1437) ------------------
#
# Anything checking the row has to build the expected one from the score,
# and building it in Python is where C-1437 came from: `Math.round` sends
# a half up, `round` sends it to the even side, so the two agree until a
# template's points put `score / per` exactly halfway and then the page
# is failed for being right. `bar_for()` is that mirror, and a mirror is
# only worth having if it is checked against the thing it reflects - so
# this runs the page's own `shareBar` and compares, rather than restating
# the rule a third time.


def _page_shareBar(spec: dict, scores: list[int]) -> list[str]:
    """The product's own shareBar, run in node over the given scores."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to run the page's own rule")
    body = SHARE_PREAMBLE[SHARE_PREAMBLE.index("function shareBar") :]
    body = body[: body.index("\nfunction ")]
    source = (
        f"const SHARE_SPEC={json.dumps(spec, ensure_ascii=False)};\n"
        f"{body}\n"
        f"console.log(JSON.stringify({json.dumps(scores)}.map(shareBar)))"
    )
    ran = subprocess.run(["node", "-"], input=source, capture_output=True, text=True, timeout=60)
    assert ran.returncode == 0, ran.stderr[:400]
    return json.loads(ran.stdout)


@pytest.mark.parametrize("template", KEYS)
def test_the_mirror_agrees_with_the_page_on_every_score_including_the_ties(
    template: str,
) -> None:
    spec = share_spec(template)
    # Far enough past `max * per` that the clamp is exercised too, and
    # dense enough that every half-way point in range is in the list.
    scores = list(range(0, spec["per"] * (spec["max"] + 2) + 1))

    theirs = _page_shareBar(spec, scores)
    mine = [bar_for(score, spec) for score in scores]

    assert mine == theirs
    # A whole score can only land halfway when `per` is even, so an odd
    # one cannot reach the disagreement at all. Which templates those
    # are is not fixed - `per` is derived from the skin unit and moves -
    # so the tie is asserted where it exists rather than assumed.
    ties = [s for s in scores if (s / spec["per"]) % 1 == 0.5]
    assert bool(ties) is (spec["per"] % 2 == 0)


def test_the_python_builtin_would_have_disagreed() -> None:
    """The bug this replaced, pinned so nobody quietly puts it back.

    Not a claim about `bar_for` - a claim about why it cannot be one
    line of `round()`. Were that true, the two would agree here.
    """

    spec = {"emoji": "x", "max": 10, "per": 12}
    # 78 / 12 is exactly 6.5: the page draws seven, `round` wants six.
    assert bar_for(78, spec) == "x" * 7
    assert round(78 / spec["per"]) == 6


def test_some_template_can_actually_reach_the_halfway_score() -> None:
    """Otherwise the test above passes by never meeting the case.

    If every `per` went odd this would stop guarding anything, and it
    should say so rather than going quietly green.
    """

    reachable = [k for k in KEYS if share_spec(k)["per"] % 2 == 0]

    assert reachable, "no template can land on a half; the tie is untested"


@pytest.mark.parametrize("template", KEYS)
def test_the_page_carries_this_sides_spec_rather_than_one_of_its_own(template: str) -> None:
    """What the row is checked against has to be independent of the page.

    The expected row is built from `share_spec()`, not from the per/max/
    emoji the page reports about itself - a check that used the page's
    own numbers would pass a page that shipped the wrong ones, which is
    the same self-agreement C-1427 found in a different counter. That is
    only sound while the two are actually the same object, so they are
    held to each other here.

    What this can see, and what it cannot: both sides read `share_spec()`,
    so changing that function moves them together and this stays green
    (measured - a deliberate `per + 1` there passed). What it catches is
    the path between the two, which is where they can actually come
    apart: a `preamble_for` building the token out of anything else
    fails it (measured, `per=8` in the token: four templates red).
    """

    page = generate_game(REQUEST, template=template).html
    carried = re.search(r"const SHARE_SPEC=(\{.*?\});", page, re.S)

    assert carried is not None, "the page declares no spec"
    assert json.loads(carried.group(1)) == share_spec(template)
