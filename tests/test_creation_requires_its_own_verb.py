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


def test_the_undecidable_six_say_why_in_words() -> None:
    """And the reason has to be about the measurement.

    A template listed here is NOT being called badly designed. Three of them
    use the arrow keys as the verb, so there is nothing to withhold; the rest
    are not finished by a wanderer inside a round. If a reason ever starts
    describing the template as lacking something, this list has quietly turned
    into an accusation the measurement cannot support.
    """

    for key, why in VERB_UNDECIDABLE.items():
        assert len(why.strip()) > 20, key
        assert "分けられない" in why or "抜く相手が無い" in why or "抜いても" in why, key


def test_the_judge_shows_four_and_says_so() -> None:
    result = evaluate_requires_its_own_verb()
    assert result.failures == ()
    assert result.passed
    assert result.shown == len(VERB_TEMPLATES) == 4
    assert result.decided == ("duel", "fishing", "kaiju", "shooter")
    assert result.checks_total == result.checks_passed + len(result.failures)


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
