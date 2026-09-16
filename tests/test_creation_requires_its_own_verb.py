"""The verb is needed, and the sample says what it covers (C-1884).

§34 事実 1 gives the test: an agent that cannot perform a mechanic must not be
able to beat a level that teaches it. §34 事実 2 gives the trap, and these
tests are mostly about the trap - the crippled agent has to be competent
otherwise, so a judge that counts a wanderer's failures as evidence is
counting badness, not missing mechanics.
"""

from __future__ import annotations

from sidra_ai.creation.games import TEMPLATES
from sidra_ai.evals.requires_its_own_verb import (
    FRAMES,
    VERB_TEMPLATES,
    VERB_UNDECIDABLE,
    evaluate_requires_its_own_verb,
)


def test_every_template_is_either_decided_or_explained() -> None:
    decided, explained = set(VERB_TEMPLATES), set(VERB_UNDECIDABLE)
    assert decided & explained == set()
    assert decided | explained == set(TEMPLATES)


def test_the_undecidable_ones_say_why_in_words() -> None:
    """And the reason has to be about the measurement.

    A template listed here is NOT being called badly designed. Each one needs
    an agent that can finish something - a dungeon, a course, a board - and
    none exists yet. If a reason ever starts describing the template as
    lacking something, this list has quietly turned into an accusation the
    measurement cannot support.

    C-1885 is why the wording matters. Three templates sat here with the
    reason 「矢印そのものが動詞なので抜く相手が無い」, which sounded like a fact
    about them and was a fact about the agent: there was plenty to withhold,
    and the missing piece was competence on the other side. A reason phrased
    as 「まだ無い」 is a reason somebody can remove.
    """

    for key, why in VERB_UNDECIDABLE.items():
        assert len(why.strip()) > 20, key
        assert "まだ無い" in why, key
        assert "分けられない" in why, key


def test_the_judge_shows_seven_and_says_so() -> None:
    result = evaluate_requires_its_own_verb()
    assert result.failures == ()
    assert result.passed
    assert result.shown == len(VERB_TEMPLATES) == 7
    assert result.decided == (
        "catch", "duel", "fishing", "kaiju", "marble", "racing", "shooter",
    )
    assert result.checks_total == result.checks_passed + len(result.failures)


def test_the_two_kinds_of_verb_are_crippled_differently() -> None:
    """A space template loses its action key; a steer template loses the arrows.

    Withholding space from a game whose verb IS the arrows takes nothing away,
    which is exactly the mistake the old ``VERB_UNDECIDABLE`` entry recorded as
    a property of the template.
    """

    kinds = {key: spec["kind"] for key, spec in VERB_TEMPLATES.items()}
    assert set(kinds.values()) == {"space", "steer"}
    assert {k for k, v in kinds.items() if v == "steer"} == {"racing", "catch", "marble"}


def test_the_steering_agent_asks_the_page_where_to_go() -> None:
    """racing publishes ``roadAt(d)``; the judge must not carry a second copy.

    The course is two seeded sines. Re-deriving them inside the probe is the
    drift C-1640 stopped when it made the palette judge read the running page
    instead of the table, and racing's own notes say the probe may ask.
    """

    from sidra_ai.evals.requires_its_own_verb import _HARNESS

    assert "roadAt(dist)" in _HARNESS
    assert "Math.sin" not in _HARNESS


def test_the_number_is_coverage_and_not_a_score_out_of_four() -> None:
    """Four out of ten, not four out of four.

    The judge reports how much of the product this method could decide. Read
    as a score over ``VERB_TEMPLATES`` it would always be full marks, and
    adding a template nobody can measure would raise it.
    """

    result = evaluate_requires_its_own_verb()
    assert result.shown < len(TEMPLATES)


def test_the_run_is_long_enough_to_separate_them() -> None:
    """FRAMES is a real parameter, not a round number.

    At 60fps this is thirty seconds of play after the gate. Shorter and the
    four stop separating; the first measurement used 3800 and this is the
    shortest that still decides all four, which is what keeps eight node runs
    inside the collector's budget.
    """

    assert 1200 <= FRAMES <= 2400
