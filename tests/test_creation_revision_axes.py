"""Every dial the page has, reachable by a sentence.

C-1112 gave the revision loop three axes - difficulty, theme, title -
while C-1113 put six adjustable parameters in every generated page. The
gap was the interesting part: a person could move a slider that words
could not reach, which is §9's "ask again and get something different"
trap one level down.

Speed is deliberately not an axis of its own. The difficulty ladder *is*
what changes speed, and a second speed axis would let the two disagree
about what 「速く」 means - the item said so, and this file pins it.

What made the judging honest here was one thing learned in C-1119: a
declared default is not a fact about the product. The first version of
these checks read the schema the page embeds, and a flag whose default
never reached ``dailyOn()`` still looked like a change. The two switches
are now asked of the running page.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.games import _DIFFICULTY, generate_game, save_game  # noqa: E402
from sidra_ai.creation.revise import (  # noqa: E402
    _ACCENT_WORDS,
    _step_band,
    build_game_reviser,
    detect_revision_intent,
    save_meta,
)
from sidra_ai.creation.together import probe_source  # noqa: E402
from sidra_ai.creation.tuning import panel_schema  # noqa: E402

TEMPLATE = "adventure"
REQUEST = "冒険ゲームを作って"


def _fresh(home: str) -> Path:
    built = generate_game(REQUEST, template=TEMPLATE)
    page = save_game(built, home)
    save_meta(
        page,
        request=REQUEST,
        template=TEMPLATE,
        difficulty=built.difficulty,
        theme="",
        title=built.title,
        panel={},
    )
    return page


def _read(path) -> tuple[dict, str, str]:
    text = Path(path).read_text(encoding="utf-8")
    body = re.search(r"<script>(.*?)</script>", text, re.S).group(1)
    spec = re.search(r"const TUNE_SPEC=(\{.*?\});", body, re.S).group(1)
    return {f["key"]: f["default"] for f in json.loads(spec)["fields"]}, body, text


def _say(home: str, sentence: str):
    intent = detect_revision_intent(sentence)
    assert intent.is_revision, f"「{sentence}」 was not read as a revision"
    return build_game_reviser(home)(sentence, intent)


def _running(body: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to ask the page")
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(
            body,
            speed_expr="0",
            frames=6,
            quiet=True,
            reduced=True,
            stored={f"sidra.seen.{TEMPLATE}": "1"},
        ),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


# --------------------------------------------------------------- the axes


@pytest.mark.parametrize(
    ("sentence", "axis", "direction"),
    [
        ("さっきのゲームの敵を減らして", "band", "down"),
        ("さっきのゲームの敵を増やして", "band", "up"),
    ],
)
def test_the_second_axis_moves_both_ways(sentence: str, axis: str, direction: str) -> None:
    with tempfile.TemporaryDirectory() as home:
        page = _fresh(home)
        before, _, _ = _read(page)
        after, _, _ = _read(_say(home, sentence).artifact_path)

    assert (after[axis] < before[axis]) if direction == "down" else (after[axis] > before[axis])


def test_an_axis_stays_inside_the_span_its_author_shipped() -> None:
    """Ten widenings do not walk off the end of the panel."""

    steps = sorted({pair[1] for pair in _DIFFICULTY[TEMPLATE].values()})
    value = steps[0]
    for _ in range(10):
        value = _step_band(TEMPLATE, value, "+1")

    assert value == steps[-1]


def test_the_accent_is_the_colour_that_was_asked_for() -> None:
    with tempfile.TemporaryDirectory() as home:
        _fresh(home)
        after, _, text = _read(_say(home, "さっきのゲームを赤にして").artifact_path)

    assert after["accent"] == _ACCENT_WORDS["赤"]
    assert _ACCENT_WORDS["赤"] in text


@pytest.mark.parametrize(
    ("sentence", "flag"),
    [
        ("さっきのゲームを日替わりにして", "daily"),
        ("さっきのゲームのブリーフィングを毎回出して", "brief"),
    ],
)
def test_a_switch_reaches_the_running_page(sentence: str, flag: str) -> None:
    """Asked of the page, not of the schema.

    A default that never reaches ``dailyOn()`` still reads as changed if
    you only look at the declaration - the mistake C-1119 caught in a
    different judge, made once here too.
    """

    with tempfile.TemporaryDirectory() as home:
        page = _fresh(home)
        _, before_body, _ = _read(page)
        _, after_body, _ = _read(_say(home, sentence).artifact_path)

    was, now = _running(before_body), _running(after_body)
    if flag == "daily":
        assert was["atLoad"]["round"]["daily"] is False
        assert now["atLoad"]["round"]["daily"] is True
    else:
        assert was["atLoad"]["gate"]["skipped"] is True
        assert now["atLoad"]["gate"]["skipped"] is False


def test_a_switch_can_be_turned_back_off() -> None:
    """「やめて」 is an instruction with no して in it, which the change-verb
    veto used to decline."""

    with tempfile.TemporaryDirectory() as home:
        _fresh(home)
        _say(home, "さっきのゲームを日替わりにして")
        _, body, _ = _read(_say(home, "さっきのゲームの日替わりをやめて").artifact_path)

    assert _running(body)["atLoad"]["round"]["daily"] is False


# ------------------------------------------------------------- the chain


def test_a_later_sentence_does_not_undo_an_earlier_one() -> None:
    """The whole reason the sidecar carries the panel."""

    with tempfile.TemporaryDirectory() as home:
        _fresh(home)
        narrowed, _, _ = _read(_say(home, "さっきのゲームの敵を減らして").artifact_path)
        later, _, text = _read(_say(home, "さっきのゲームのタイトルを「続き」にして").artifact_path)

    assert later["band"] == narrowed["band"]
    assert "続き" in text


def test_a_new_difficulty_re_reads_both_axes() -> None:
    """Difficulty owns speed *and* band, so a later difficulty word must not
    leave a stale band beside it - the two would disagree about the page."""

    with tempfile.TemporaryDirectory() as home:
        _fresh(home)
        _say(home, "さっきのゲームの敵を減らして")
        after, _, _ = _read(_say(home, "さっきのゲームを難しくして").artifact_path)

    assert after["band"] == _DIFFICULTY[TEMPLATE]["hard"][1]
    assert after["speed"] == _DIFFICULTY[TEMPLATE]["hard"][0]


# ------------------------------------------------- what the page cannot say


def test_speed_is_not_an_axis_of_its_own() -> None:
    """The ladder is the speed axis. Two would let them disagree."""

    assert detect_revision_intent("さっきのゲームを速くして").adjustments == {"difficulty": "+1"}
    assert detect_revision_intent("さっきのゲームを遅くして").adjustments == {"difficulty": "-1"}


def test_creation_and_questions_are_still_not_stolen() -> None:
    for sentence in (
        "難しいゲームを作って",
        "難しいゲームを作成して",
        "冒険ゲームを生成して",
        "ゲームを難しくできますか",
    ):
        assert detect_revision_intent(sentence).is_revision is False


def test_an_overridden_axis_is_clamped_to_the_panel() -> None:
    """Storage and sidecars are both editable by hand; neither may take the
    game outside the range its author shipped."""

    bands = [pair[1] for pair in _DIFFICULTY[TEMPLATE].values()]
    schema = panel_schema(
        TEMPLATE, _DIFFICULTY[TEMPLATE], difficulty="normal", accent="#000000",
        overrides={"band": 10**6},
    )
    field = next(f for f in schema["fields"] if f["key"] == "band")

    assert field["default"] == max(bands)
