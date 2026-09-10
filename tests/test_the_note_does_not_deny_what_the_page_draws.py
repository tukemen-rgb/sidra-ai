"""C-1525: the honesty note was lying, in the direction it exists to prevent.

「巨大な敵と戦うゲームを作って」 came back as 「『巨獣迎撃戦』型で作りました。
ただし「敵」は絵として出てきません」 - one sentence contradicting itself about
a page whose entire content is the enemy. 「3D のコースを転がるゲームを作って」
said the same about the course.

C-1514 fixed the *wording* of these quotes (「コースを」 -> 「コース」) and
nobody checked whether the word that survived was something the page really
could not draw. Measured across the ten templates: **two** got it right and
eight denied something they draw - kaiju 敵, marble コース, shooter 敵,
adventure 宝, racing コース, duel 相手, puzzle ブロック, catch 皿.

What the page draws is read from what the page already tells the player -
the start screen's three briefing lines and the 操作説明 - rather than from a
list written for this question, so the two cannot drift apart the way
C-1120's three hand-written vocabularies did.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.games import (
    TEMPLATES,
    generate_game,
    template_depicts,
    undepicted_subject,
)

#: For each template: a request naming something the page really draws, and
#: one naming something it really does not. Both route to the same template,
#: so the pair differs in exactly one thing.
PAIRS: dict[str, tuple[str, str]] = {
    "kaiju": ("巨大な敵と戦うゲームを作って", "巨大な猫と戦うゲームを作って"),
    "marble": ("3D のコースを転がるゲームを作って", "3D の猫を転がすゲームを作って"),
    "shooter": ("弾幕の敵を撃つゲームを作って", "弾幕の猫を撃つゲームを作って"),
    "adventure": ("ダンジョンの宝を探すゲームを作って", "ダンジョンの猫を探すゲームを作って"),
    "racing": ("レースのコースを走るゲームを作って", "レースの猫を走らせるゲームを作って"),
    "duel": ("ビームの相手と戦うゲームを作って", "ビームの猫と戦うゲームを作って"),
    "puzzle": ("パズルのブロックを消すゲームを作って", "パズルの猫を消すゲームを作って"),
    "platformer": ("ジャンプの足場を渡るゲームを作って", "ジャンプの猫を渡すゲームを作って"),
    "fishing": ("釣りの魚を釣るゲームを作って", "釣りの猫を釣るゲームを作って"),
    "catch": ("キャッチの受け皿で拾うゲームを作って", "キャッチの猫を拾うゲームを作って"),
}


def _note_for(request: str) -> tuple[str, str]:
    game = generate_game(request)
    return game.template, undepicted_subject(request, game.template, game.asked_title)


def test_the_pairs_cover_every_template() -> None:
    """A pair that quietly stopped covering a template would shrink the
    measurement without changing its name."""

    assert set(PAIRS) == set(TEMPLATES)


@pytest.mark.parametrize("template", sorted(PAIRS))
def test_both_halves_of_a_pair_reach_the_same_template(template: str) -> None:
    drawn, absent = PAIRS[template]

    assert _note_for(drawn)[0] == template
    assert _note_for(absent)[0] == template


@pytest.mark.parametrize("template", sorted(PAIRS))
def test_the_note_is_silent_about_what_the_page_draws(template: str) -> None:
    """The defect itself."""

    assert _note_for(PAIRS[template][0])[1] == ""


@pytest.mark.parametrize("template", sorted(PAIRS))
def test_the_note_still_speaks_about_what_the_page_does_not_draw(template: str) -> None:
    """The other side. Deleting the note passes the test above on all ten
    templates and fixes nothing - C-1205 built it for exactly these
    requests."""

    assert _note_for(PAIRS[template][1])[1] == "猫"


def test_the_requests_c1205_was_built_for_are_untouched() -> None:
    """The named examples from the note's own history keep their caveat."""

    for request, expected in (
        ("猫のゲームを作って", "猫"),
        ("魚の 3D ゲームを作って", "魚"),
        ("宝石を拾うゲームを作って", "宝石"),
        ("犬が走るゲームを作って", "犬"),
        ("宇宙を旅するゲームを作って", "宇宙"),
        ("ドラゴンを育てるゲームを作って", "ドラゴン"),
    ):
        assert _note_for(request)[1] == expected, request


# --- where the answer comes from -------------------------------------


@pytest.mark.parametrize(
    "template,word",
    [
        ("marble", "コース"),
        ("racing", "コース"),
        ("adventure", "宝"),
        ("shooter", "敵"),
        ("duel", "相手"),
        ("catch", "皿"),
        ("platformer", "足場"),
    ],
)
def test_the_pages_own_words_are_the_source(template: str, word: str) -> None:
    """Seven of the ten need no list at all: the page says it draws these,
    in the copy the player reads.

    Seven, not eight - this test caught the miscount. fishing's pair passes
    for an older reason entirely: 「魚」 is one of FISHING_WORDS, so the
    genre trimming takes it off long before the depiction check is reached,
    and fishing's copy never says 魚 at all (it talks about the band and
    the marker). Counting it here would have credited this item with a case
    it does not touch.
    """

    said = TEMPLATES[template].how_to_play
    from sidra_ai.creation.startscreen import BRIEFINGS

    said = f"{said} {' '.join(BRIEFINGS.get(template, ()))}"

    assert word in said
    assert template_depicts(template, word)


@pytest.mark.parametrize("template,word", [("kaiju", "敵"), ("puzzle", "ブロック")])
def test_only_two_pages_answer_in_a_synonym(template: str, word: str) -> None:
    """...and those two are declared, with the object they stand for named
    in the comment. Declared *because* the copy does not say it - if the
    copy did, the list would be the drift C-1120 fixed."""

    from sidra_ai.creation.startscreen import BRIEFINGS

    said = f"{TEMPLATES[template].how_to_play} {' '.join(BRIEFINGS.get(template, ()))}"

    assert word not in said, "the copy says it, so the synonym is redundant"
    assert template_depicts(template, word)


def test_a_page_does_not_claim_another_templates_contents() -> None:
    """The check is per template, not a shared pool: fishing does not draw
    a course, and must still say so."""

    assert not template_depicts("fishing", "コース")
    assert not template_depicts("kaiju", "受け皿")
    assert not template_depicts("puzzle", "巨獣")
