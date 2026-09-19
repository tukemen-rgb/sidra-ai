"""The canvas word table, pinned where a judge cannot see it (C-1959).

``creation_catch_canvas_matches_the_language_asked`` plays one go and reads
what the canvas drew. Some of the shared words only appear under conditions
one go does not reach - a personal best, a daily streak, a run history, a
newly opened skin - so they are held here instead, and this file says so
rather than letting the gap go unrecorded.
"""

from __future__ import annotations

import re
from pathlib import Path

from sidra_ai.creation.canvaswords import CANVAS_WORDS, words_js
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.round import ROUND_SCORE, ROUND_SCORE_EN, ROUND_TIE, ROUND_TIE_EN

JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")


def test_every_word_has_both_languages() -> None:
    from sidra_ai.creation.canvaswords import EMPTY_IN_ENGLISH

    for key, pair in CANVAS_WORDS.items():
        assert pair[0], key
        # 「個」 and 「回」 are counters a number says by itself in English,
        # so their English column is empty ON PURPOSE and named (C-1960).
        assert pair[1] or key in EMPTY_IN_ENGLISH, key
        assert not JAPANESE.search(pair[1]), f"{key} is still Japanese in English"


def test_every_word_is_actually_named_by_some_template() -> None:
    """A row nothing names is a word that cannot reach a player.

    Read across the package rather than off one page: since C-1960 the rows
    belong to different templates, and a catch page has no reason to name
    puzzle's hammer.
    """

    source = "".join(
        path.read_text(encoding="utf-8")
        for path in sorted(Path("src/sidra_ai/creation").glob("*.py"))
    )
    unused = [key for key in CANVAS_WORDS if f"CW.{key}" not in source]
    assert unused == [], f"CANVAS_WORDS rows nothing names: {unused}"


def test_the_english_column_reaches_the_english_page() -> None:
    page = generate_game("make a catching game about an owl").html
    words = words_js(in_japanese=False)
    assert words.strip() in page.replace("\n", "\n")
    # The English word has to be IN the page; the Japanese one being absent
    # cannot be asserted here, because the script ships its own comments and
    # those are written in Japanese (C-1956 measured 174 such lines, none of
    # them drawn). What is drawn is the judge's question, not this file's.
    for key in ("best", "daily", "recent", "unlock_open", "cant_clear", "got_away"):
        assert CANVAS_WORDS[key][1] in page, key


def test_the_japanese_page_keeps_the_words_it_always_had() -> None:
    page = generate_game("ふくろうのキャッチゲームを作って").html
    for key in ("best", "daily", "recent", "unlock_open", "time_up", "again"):
        assert CANVAS_WORDS[key][0] in page, key


def test_every_template_has_an_english_score_label() -> None:
    assert set(ROUND_SCORE) == set(ROUND_SCORE_EN)
    assert set(ROUND_TIE) == set(ROUND_TIE_EN)
    for label in list(ROUND_SCORE_EN.values()) + list(ROUND_TIE_EN.values()):
        assert not JAPANESE.search(label), label


def test_the_recap_lines_are_translated_or_named() -> None:
    """Every wired template is in exactly one of the two lists (C-1960)."""

    from sidra_ai.creation.recap import LOSS_WIRED, LOSS_WIRED_EN, RECAP_UNTRANSLATED

    for key in LOSS_WIRED:
        assert (key in LOSS_WIRED_EN) != (key in RECAP_UNTRANSLATED), key
    for key, lines in LOSS_WIRED_EN.items():
        assert len(lines) == len(LOSS_WIRED[key]["causes"]), key
        for line in lines:
            assert not JAPANESE.search(line), key


def test_english_requests_reach_every_template() -> None:
    """C-1960 measured that no English phrasing reached marble at all."""

    from sidra_ai.creation.games import choose_template
    from sidra_ai.evals.canvas_matches_the_language_asked import TEMPLATE_ASKS

    for key, ask in TEMPLATE_ASKS.items():
        assert choose_template(ask) == key, f"{ask!r} does not reach {key}"


def test_adventure_marks_and_rooms_are_in_the_language_asked() -> None:
    """What one unattended go never reaches, read off the page anyway.

    C-1964's judge plays a go and reads what the canvas drew, which is the
    right question - but an untouched hero never leaves the first room, so
    the cave marks and the other two room names are never painted in that
    run. Reverting them to kanji was measured and the judge stayed at
    10/10: a sabotage that does not go red is evidence about the judge, so
    the gap is pinned here instead of being left to look covered.

    This is still the page rather than the table: the script is run and its
    own ``KMARKS`` and ``NAMES`` are read back out of it.
    """

    import json
    import re
    import shutil
    import subprocess

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        return

    from sidra_ai.creation.hudpaint import text_probe

    def marks(ask: str) -> dict:
        page = generate_game(ask).html
        script = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
        probe = text_probe(script).replace(
            "console.log(JSON.stringify({ hud: hudFacts(), ops: paintOps }));",
            "console.log(JSON.stringify({ marks: KMARKS, rooms: NAMES }));",
        )
        run = subprocess.run(
            ["node", "-"], input=probe, capture_output=True, text=True, timeout=600
        )
        assert run.returncode == 0, run.stderr[-400:]
        return json.loads(run.stdout.strip().splitlines()[-1])

    english = marks("make an adventure game about an owl")
    for word in english["marks"] + english["rooms"]:
        assert not JAPANESE.search(word), f"the English page still draws {word!r}"

    japanese = marks("ふくろうの冒険ゲームを作って")
    assert japanese["marks"] == ["月", "星", "日"]
    assert any(JAPANESE.search(word) for word in japanese["rooms"])
