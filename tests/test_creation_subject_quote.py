"""The honesty note must quote the operator, not a phrase we assembled (C-1503).

「ただし「X」は絵として出てきません」 puts X in quotation marks as the
operator's own words. X was built by deleting the genre word wherever it fell
and then the fillers the same way, so it quoted them saying things they never
typed:

* 「落ちてくるものをキャッチするゲームを作って」 → 「落ちてくるもをする」
  - キャッチ taken from the middle, then the 「の」 *inside* 「もの」 taken
    with the fillers;
* 「忍者のアクションゲームを作って」 → 「忍者アクション」;
* 「怪獣を倒すゲームを作って」 → 「を倒す」, which IS a run of the request
  and is still grammar rather than subject.

The fix trims from the ends only, so what survives is a contiguous run of
their characters by construction, and then checks it. Both halves are tested:
the broken quotes have to stop, AND the note has to keep appearing for the
two cases it was built for (C-1205) - a version that simply never spoke would
satisfy every "no bad quote" assertion and would not be a fix.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.games import generate_game, undepicted_subject

#: Glue a caveat must never open with.
GLUE = ("を", "が", "に", "へ", "と", "で", "の", "は", "も", "や")

SAYS_NOTHING = (
    # The genre word sits inside the subject and cannot be cut out of it.
    # The page did build a catch game, so naming the whole phrase would be
    # a lie in the other direction.
    "落ちてくるものをキャッチするゲームを作って",
    # Trimming the genre word off the front leaves a particle.
    "怪獣を倒すゲームを作って",
    # Nothing was promised beyond the genre.
    "レースゲームを作って",
    "ゲームを作って",
)

SPEAKS = (
    # C-1205's own two examples: a subject the page does not draw.
    "猫のゲームを作って",
    "魚の 3D ゲームを作って",
    "忍者のアクションゲームを作って",
    "宇宙を旅するゲームを作って",
    "犬が走るゲームを作って",
    "ドラゴンを育てるゲームを作って",
    "お寿司を集めるゲームを作って",
    "宝石を拾うゲームを作って",
)


def subject_for(request: str) -> str:
    game = generate_game(request)
    return undepicted_subject(request, game.template, game.asked_title)


# ------------------------------------------------------------ the defect


@pytest.mark.parametrize("request_text", SAYS_NOTHING + SPEAKS)
def test_every_quote_is_the_operators_own_words(request_text: str) -> None:
    """A contiguous run of the request, or nothing at all."""

    subject = subject_for(request_text)
    if subject:
        assert subject in request_text


@pytest.mark.parametrize("request_text", SAYS_NOTHING + SPEAKS)
def test_no_quote_opens_with_a_particle(request_text: str) -> None:
    subject = subject_for(request_text)
    if subject:
        assert not subject.startswith(GLUE)


def test_the_reported_broken_quotes_are_gone() -> None:
    """The three the item names, by the strings it names them with."""

    assert subject_for("落ちてくるものをキャッチするゲームを作って") == ""
    assert subject_for("怪獣を倒すゲームを作って") == ""
    assert subject_for("忍者のアクションゲームを作って") == "忍者のアクション"


# ------------------------------------------------------- the other half


@pytest.mark.parametrize("request_text", SPEAKS)
def test_the_note_still_speaks_where_it_was_built_to(request_text: str) -> None:
    """Silence would pass every assertion above and fix nothing."""

    assert subject_for(request_text)


def test_a_single_character_subject_is_kept() -> None:
    """C-1205's two examples, and the reason there is no minimum length.

    The item suggested rejecting a one-character residue as debris. Measured,
    that silenced 「猫」 and 「魚」 - both real subjects. A one-character
    residue that is debris is a particle, and the particle rule has it.
    """

    assert subject_for("猫のゲームを作って") == "猫"
    assert subject_for("魚の 3D ゲームを作って") == "魚"


@pytest.mark.parametrize(
    "ask, said",
    [
        # No genre was named, so the summary says the subject has no
        # template at all...
        ("猫のゲームを作って", "「猫」の題材を描く型はまだ無い"),
        # ...and when the genre WAS honoured, the caveat is the 「ただし」
        # form: the 3D course exists, the fish does not.
        ("魚の 3D ゲームを作って", "ただし「魚」は絵として出てきません"),
    ],
)
def test_the_caveat_reaches_the_summary_a_person_reads(ask: str, said: str) -> None:
    """Not just the helper: the sentence the operator is shown.

    Both wordings are checked because they come from different branches and
    the quote flows into each of them - a fix that only reached one would
    leave the other quoting debris.
    """

    import tempfile

    from sidra_ai.creation.game_job import build_game_generator
    from sidra_ai.creation.intent import detect_creation_intent

    with tempfile.TemporaryDirectory() as folder:
        outcome = build_game_generator(folder)(ask, detect_creation_intent(ask))
        assert said in outcome.summary, outcome.summary


def test_the_caveat_is_absent_where_the_quote_would_be_broken() -> None:
    from sidra_ai.creation.game_job import build_game_generator
    from sidra_ai.creation.intent import detect_creation_intent
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        ask = "落ちてくるものをキャッチするゲームを作って"
        outcome = build_game_generator(folder)(ask, detect_creation_intent(ask))
        assert "絵として出てきません" not in outcome.summary
