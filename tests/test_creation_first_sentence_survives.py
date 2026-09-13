"""C-1764: what the first sentence turned is still there after the second.

``save_meta`` has taken a ``panel=`` argument since C-1117, and the comment
directly above it says what happens without one: a later sentence rebuilds
from the ladder and quietly undoes what the earlier one turned. Only
``revise.py`` ever passed it. ``game_job.py`` - the path every operator
takes, because it is the one that makes the first page - recorded ``{}``.

The existing chain test (``test_creation_revision_axes``) did not catch it
because its fixture hand-writes the sidecar with ``panel={}`` and starts the
chain at the second sentence. The first sentence's turn was never in the
chain being tested.

Both directions are pinned here, because carrying the panel forward too
eagerly is its own bug: a revision that names a row has to still move it.
And C-1710 is pinned as a sentinel - a new difficulty re-reads both axes
and so drops a chosen band ON PURPOSE, which it must say out loud.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.game_job import build_game_generator  # noqa: E402
from sidra_ai.creation.games import _DIFFICULTY  # noqa: E402
from sidra_ai.creation.games import PROPOSABLE_ROWS, _panel_in_force  # noqa: E402
from sidra_ai.creation.intent import detect_creation_intent  # noqa: E402
from sidra_ai.creation.revise import (  # noqa: E402
    build_game_reviser,
    detect_revision_intent,
    meta_path_for,
)
from sidra_ai.creation.tuning import AXIS_LABELS, panel_schema  # noqa: E402

REQUEST = "パズルゲームを作って"
TEMPLATE = "puzzle"
BANDS = tuple(pair[1] for pair in _DIFFICULTY[TEMPLATE].values())
# The band the first sentence asks for has to differ from BOTH the rung the
# page would otherwise open on (normal) and the rung 「難しくして」 moves it
# to (hard). Otherwise the carry has nothing to prove, or - the mistake this
# file was written with - C-1710 stays correctly silent because the number
# it would announce did not actually change, and the silence reads as a bug
# that is not there.
_NORMAL_BAND = _DIFFICULTY[TEMPLATE]["normal"][1]
_HARD_BAND = _DIFFICULTY[TEMPLATE]["hard"][1]
CHOSEN = next(v for v in sorted(set(BANDS)) if v not in (_NORMAL_BAND, _HARD_BAND))
#: Which way 「帯を…」 can still move from there, and the word for it.
WIDER = CHOSEN < max(BANDS)
MOVE_WORD = "そのゲームの帯を広くして" if WIDER else "そのゲームの帯を狭くして"
MOVE_DELTA = "+1" if WIDER else "-1"
ASKED = {"band": CHOSEN, "accent": "#4fd1c5", "daily": True, "brief": True}


def _spec(path) -> dict:
    body = re.search(r"<script>(.*?)</script>", Path(path).read_text(encoding="utf-8"), re.S)
    assert body is not None
    spec = re.search(r"const TUNE_SPEC=(\{.*?\});", body.group(1), re.S)
    assert spec is not None
    return {f["key"]: f["default"] for f in json.loads(spec.group(1))["fields"]}


def _pages(home) -> list[Path]:
    return sorted(Path(home).rglob("*.html"))


def _make(home, proposal=None):
    generate = build_game_generator(home, None, (lambda m, t, s: dict(proposal)) if proposal else None)
    generate(REQUEST, detect_creation_intent(REQUEST))
    return _pages(home)[-1]


def _say(home, sentence, *, expect: dict):
    intent = detect_revision_intent(sentence)
    assert intent.is_revision, f"「{sentence}」 was not read as a revision"
    assert intent.adjustments == expect, intent.adjustments
    before = set(_pages(home))
    outcome = build_game_reviser(home)(sentence, intent)
    after = [p for p in _pages(home) if p not in before]
    return (after[-1] if after else None), outcome


# ---------------------------------------------------------- the recording


def test_the_build_records_the_rows_the_sentence_turned() -> None:
    with tempfile.TemporaryDirectory() as home:
        page = _make(home, ASKED)
        recorded = json.loads(meta_path_for(page).read_text(encoding="utf-8"))["panel"]

    assert recorded == ASKED


def test_the_record_is_what_the_page_opens_with_not_what_was_asked() -> None:
    """A band outside the author's span is clamped, and the clamped number
    is what gets written down - a record that disagrees with the screen is
    the failure C-1744 was about."""

    absurd = dict(ASKED, band=max(BANDS) * 10)
    with tempfile.TemporaryDirectory() as home:
        page = _make(home, absurd)
        recorded = json.loads(meta_path_for(page).read_text(encoding="utf-8"))["panel"]
        opened = _spec(page)

    assert recorded["band"] == max(BANDS)
    assert opened["band"] == recorded["band"]


def test_a_build_nobody_tuned_records_nothing() -> None:
    """"Nobody chose a band" has to stay distinguishable from "somebody
    chose the one the ladder would have picked" - C-1710 announces a
    dropped band, and must not announce a drop nobody asked for."""

    with tempfile.TemporaryDirectory() as home:
        page = _make(home)
        recorded = json.loads(meta_path_for(page).read_text(encoding="utf-8"))["panel"]

    assert recorded == {}


def test_only_rows_a_sentence_can_turn_are_recorded() -> None:
    """Volume, haptics and reduced motion are the player's, set in their
    browser on their device. A build record is not where they live."""

    schema = panel_schema(
        TEMPLATE, _DIFFICULTY[TEMPLATE], difficulty="normal", accent="#ffffff",
        overrides={"band": CHOSEN, "volume": 20, "haptic": False, "motion": True},
    )
    kept = _panel_in_force(schema, {"band": CHOSEN, "volume": 20, "haptic": False, "motion": True})

    assert kept == {"band": CHOSEN}
    assert set(PROPOSABLE_ROWS) == {"band", "accent", "daily", "ghost", "brief"}


def test_a_row_this_template_does_not_show_is_not_recorded() -> None:
    """`ghost` is a row on some templates and absent on others. A value for
    a row the page has no control for is not a thing the operator turned."""

    schema = panel_schema(
        TEMPLATE, _DIFFICULTY[TEMPLATE], difficulty="normal", accent="#ffffff",
        overrides={"ghost": False},
    )
    shown = {f["key"] for f in schema["fields"]}
    kept = _panel_in_force(schema, {"ghost": False})

    assert kept == ({"ghost": False} if "ghost" in shown else {})


# -------------------------------------------------------------- the chain


def test_a_revision_about_the_title_leaves_every_other_row_alone() -> None:
    with tempfile.TemporaryDirectory() as home:
        page = _make(home, ASKED)
        opened = _spec(page)
        assert {k: opened[k] for k in ASKED} == ASKED

        after, _ = _say(home, "そのゲームのタイトルを「夜の欠片」に変えて", expect={"title": "夜の欠片"})
        assert after is not None
        rebuilt = _spec(after)

    assert {k: rebuilt[k] for k in ASKED} == ASKED


def test_a_revision_that_names_a_row_still_moves_it() -> None:
    """The other direction. Carrying the panel forward must not turn into
    swallowing the instruction that came with it."""

    with tempfile.TemporaryDirectory() as home:
        _make(home, ASKED)
        after, _ = _say(home, MOVE_WORD, expect={"band": MOVE_DELTA})
        assert after is not None
        moved = _spec(after)["band"]

    assert (moved > CHOSEN) if WIDER else (moved < CHOSEN)


def test_a_new_difficulty_still_says_it_dropped_the_band(monkeypatch) -> None:
    """C-1710's sentinel. Difficulty owns both axes, so it drops a chosen
    band deliberately - and a fix that carried the band through the change
    would pass the test above while silently undoing C-1710."""

    with tempfile.TemporaryDirectory() as home:
        _make(home, ASKED)
        _, outcome = _say(home, "そのゲームを難しくして", expect={"difficulty": "+1"})

    # Named with this template's own axis word - 「盤の幅」 for a puzzle,
    # 「当たり判定の幅」 for fishing - and with both numbers, because the
    # operator asked for one of them a sentence ago.
    label = AXIS_LABELS[TEMPLATE][1]
    assert f"{label}は難易度に合わせて" in outcome.summary, outcome.summary
    assert f"{CHOSEN:g}→{_HARD_BAND:g}" in outcome.summary, outcome.summary
