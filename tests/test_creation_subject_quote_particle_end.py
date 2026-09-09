"""C-1514: the caveat quoted a particle at the end of the phrase.

C-1503 gave the caveat a rule against *opening* with a particle, so
「怪獣を倒す」 stopped coming back as 「を倒す」. The same dishonesty read from
the other side survived: 「3D のコースを転がるゲームを作って」 left 「コースを」,
and the page told the operator that 「コースを」 is not drawn - quoting them
saying a fragment of their own sentence.

Trimmed rather than rejected. 「コースを」 becomes 「コース」, which is a caveat
that names the subject; refusing it would say nothing about a page that
really does not draw a course. The trim is anchored to the end, like every
other removal in ``undepicted_subject``, so what survives is still a
contiguous run of the operator's characters (C-1503's invariant).
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.games import TEMPLATES, _title_from, choose_template, undepicted_subject

GLUE = ("を", "が", "に", "へ", "と", "で", "の", "は", "も", "や")


def _subject(request: str) -> str:
    template = choose_template(request)
    title = _title_from(request, TEMPLATES[template].default_title)
    return undepicted_subject(request, template, title)


@pytest.mark.parametrize(
    "request_text,want",
    [
        ("3D のコースを転がるゲームを作って", "コース"),
    ],
)
def test_the_trailing_particle_is_not_part_of_the_subject(request_text, want) -> None:
    assert _subject(request_text) == want


@pytest.mark.parametrize(
    "request_text",
    [
        "山を登るゲームを作って",
        "空を飛ぶゲームを作って",
        "巨大な敵と戦うゲームを作って",
        "宝の地図を探すゲームを作って",
    ],
)
def test_the_clause_this_test_used_to_pin_as_unfixed_is_closed(request_text: str) -> None:
    """This pinned the defect until C-1524 closed it.

    C-1514 measured these while fixing the trailing particle and could not
    reach them - they end in a verb, not a particle - so it recorded
    today's behaviour here for the next loop to move. It moved: C-1524
    silences a residue that carries a case particle *and* ends like a verb.
    The assertion is inverted rather than deleted, so a regression to
    quoting the clause has to fail somewhere.
    """

    assert _subject(request_text) not in (request_text, "")
    assert len(_subject(request_text)) < 5


@pytest.mark.parametrize(
    "request_text",
    [
        "3D のコースを転がるゲームを作って",
        "山を登るゲームを作って",
        "空を飛ぶゲームを作って",
        "巨大な敵と戦うゲームを作って",
        "怪獣を倒すゲームを作って",
        "落ちてくるものをキャッチするゲームを作って",
        "猫のゲームを作って",
        "宇宙を旅するゲームを作って",
    ],
)
def test_no_quoted_subject_ends_in_a_particle(request_text: str) -> None:
    subject = _subject(request_text)
    assert not [g for g in GLUE if len(subject) > len(g) and subject.endswith(g)], (
        f"「{subject}」 ends in a particle"
    )


@pytest.mark.parametrize(
    "request_text",
    [
        "3D のコースを転がるゲームを作って",
        "山を登るゲームを作って",
        "巨大な敵と戦うゲームを作って",
        "猫のゲームを作って",
    ],
)
def test_what_is_quoted_is_still_the_operators_own_run(request_text: str) -> None:
    """C-1503's invariant: trimming from the ends can only ever leave a
    contiguous piece of what they typed."""

    subject = _subject(request_text)
    assert not subject or subject in request_text


@pytest.mark.parametrize(
    "request_text,want",
    [
        # The caveat still has to speak where a subject really is undrawn.
        ("猫のゲームを作って", "猫"),
    ],
)
def test_the_caveat_still_speaks(request_text: str, want: str) -> None:
    assert _subject(request_text) == want


@pytest.mark.parametrize(
    "request_text",
    ["怪獣を倒すゲームを作って", "落ちてくるものをキャッチするゲームを作って"],
)
def test_the_cases_c1503_silenced_stay_silent(request_text: str) -> None:
    """Trimming the end must not resurrect a phrase the earlier rule
    rejected: 「を倒す」 opens with a particle either way."""

    assert _subject(request_text) == ""


def test_a_request_that_named_nothing_says_nothing() -> None:
    """A bare 「ゲームを作って」 promised no subject, so there is no caveat.

    This is *not* a test of the ``len(left) > len(glue)`` guard in the trim.
    A break test removing that guard left every test here green, and
    checking directly showed why: a residue that is exactly one particle is
    rejected by C-1503's opening rule whether the trim consumed it first or
    not, so the guard cannot be observed through this path. It is kept as a
    statement that the loop must not eat its whole input - and recorded here
    as unproven rather than left looking covered.
    """

    assert _subject("ゲームを作って") == ""
