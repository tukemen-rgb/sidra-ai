"""C-1524: the caveat quoted a whole clause instead of the subject.

C-1503 stopped it opening with a particle, C-1514 stopped it closing with
one, and 「巨大な敵と戦うゲームを作って」 still left 「敵と戦う」 - said back
on the kaiju page, which *is* the fight-the-monster template, so the product
denied drawing the one thing it had drawn.

Both halves of the rule were measured before it was written, because either
one alone silences something real:

* A case particle alone is not enough - 「犬と猫」, 「海と山」, 「パンとご飯」
  and 「宝石と鍵」 are lists of subjects and every one carries 「と」.
* A verb ending alone is not enough - the filing warned about exactly this,
  and 「走る」, 「光る」 and 「回る」 are subjects that end like verbs.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.games import TEMPLATES, _title_from, choose_template, undepicted_subject


def _subject(request: str) -> str:
    template = choose_template(request)
    title = _title_from(request, TEMPLATES[template].default_title)
    return undepicted_subject(request, template, title)


@pytest.mark.parametrize(
    "request_text,want",
    [
        ("巨大な敵と戦うゲームを作って", "敵"),
        ("敵と戦うゲームを作って", "敵"),
        ("山を登るゲームを作って", "山"),
        ("空を飛ぶゲームを作って", "空"),
        ("宝の地図を探すゲームを作って", "宝の地図"),
        ("空に浮かぶゲームを作って", "空"),
        ("森で暮らすゲームを作って", "森"),
    ],
)
def test_a_clause_is_cut_down_to_what_it_is_about(request_text: str, want: str) -> None:
    """Cut to the head, not silenced.

    Silencing was written first and the existing suite refused it:
    ``test_the_note_still_speaks_where_it_was_built_to`` covers
    「宝石を拾うゲームを作って」 and three more whose subject the page really
    does not draw, and its docstring says silence "would pass every
    assertion above and fix nothing". The head - everything before the first
    case particle - is the noun the verb acts on, and 「の」 does not cut,
    so 「宝の地図を探す」 keeps 「宝の地図」.
    """

    assert _subject(request_text) == want


@pytest.mark.parametrize(
    "request_text,want",
    [
        ("宝石を拾うゲームを作って", "宝石"),
        ("犬が走るゲームを作って", "犬"),
        ("宇宙を旅するゲームを作って", "宇宙"),
        ("ドラゴンを育てるゲームを作って", "ドラゴン"),
        ("お寿司を集めるゲームを作って", "お寿司"),
    ],
)
def test_the_caveat_still_names_a_subject_the_page_cannot_draw(
    request_text: str, want: str
) -> None:
    """The four the full suite caught, plus the one beside them."""

    assert _subject(request_text) == want


def test_an_empty_head_is_still_refused() -> None:
    """「怪獣を倒すゲームを作って」 loses its genre word off the front, leaving
    「を倒す」 - whose head is empty. C-1503 decided that is refused, and
    cutting must not turn it into something quotable."""

    assert _subject("怪獣を倒すゲームを作って") == ""


@pytest.mark.parametrize(
    "request_text,want",
    [
        # A list of subjects. Carries 「と」 and must survive.
        ("犬と猫のゲームを作って", "犬と猫"),
        ("海と山のゲームを作って", "海と山"),
        ("パンとご飯のゲームを作って", "パンとご飯"),
        ("宝石と鍵のゲームを作って", "宝石と鍵"),
        # Ends like a verb, and is what the request was about.
        ("走るゲームを作って", "走る"),
        ("光るゲームを作って", "光る"),
        ("回るゲームを作って", "回る"),
        # Neither half applies.
        ("猫のゲームを作って", "猫"),
        ("忍者のアクションゲームを作って", "忍者のアクション"),
        ("3D のコースを転がるゲームを作って", "コース"),
    ],
)
def test_the_shapes_that_must_survive(request_text: str, want: str) -> None:
    assert _subject(request_text) == want


def test_a_case_particle_alone_does_not_silence() -> None:
    """Half the rule, on its own, eats a list of two subjects."""

    from sidra_ai.creation.games import _is_whole_clause

    assert _is_whole_clause("犬と猫") is False
    assert _is_whole_clause("敵と戦う") is True


def test_a_verb_ending_alone_does_not_silence() -> None:
    """The other half, on its own, eats the thing the filing warned about."""

    from sidra_ai.creation.games import _is_whole_clause

    assert _is_whole_clause("走る") is False
    assert _is_whole_clause("山を登る") is True
