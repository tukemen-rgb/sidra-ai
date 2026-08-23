"""The --save/--compare judgement on the answerable checker.

The completion condition judges work by exit codes, and until now the only
tool emitting them for the answerable numbers enforced floors: it could fail
a regression but could not certify an improvement. A loop that genuinely
moved the paraphrase rate would still be judged "no movement" by
``product_metrics.py --compare``, which cannot see numbers that need the
five checkouts. These tests pin the second judge's semantics so they stay
identical to the first one's: 0 moved, 1 nothing, 2 regressed.

Pure-function tests: the measurement itself needs the five checkouts and is
exercised by the script against the real corpus, not here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_answerable_regression.py"
_spec = importlib.util.spec_from_file_location("check_answerable_regression", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("check_answerable_regression", _mod)
_spec.loader.exec_module(_mod)


def _now(**overrides) -> dict:
    base = {
        "answerable_total": 7,
        "answerable_direct": 7,
        "answerable_paraphrase": 0,
        "answerable_discrimination": 27.8,
        "answerable_mrr": 0.307,
        "corpus_heads": {"tukemen-rgb/site": "aaaaaaaaaaaa"},
        "scored": {"direct": 11, "paraphrase": 7},
        "excerpt_hits_marker": 4,
        "excerpt_scored": 7,
        "game_production_answered": 3,
        "game_production_scored": 8,
    }
    base.update(overrides)
    return base


def test_no_change_is_not_movement(capsys) -> None:
    assert _mod._compare(_now(), _now()) == 1
    assert "NO MOVEMENT" in capsys.readouterr().out


def test_an_outcome_rising_is_movement(capsys) -> None:
    assert _mod._compare(_now(answerable_paraphrase=0), _now(answerable_paraphrase=1)) == 0
    out = capsys.readouterr().out
    assert "LOOP_LOG: answerable_paraphrase 0 -> 1" in out


def test_an_outcome_falling_is_a_regression() -> None:
    assert _mod._compare(_now(answerable_total=9), _now(answerable_total=7)) == 2


def test_a_guard_rising_is_not_bankable(capsys) -> None:
    """MRR going up alone must not read as completion.

    Otherwise reordering hits within the top-5 - which changes nothing an
    operator can see - becomes claimable progress, and the guard class stops
    meaning anything.
    """

    assert _mod._compare(_now(answerable_mrr=0.307), _now(answerable_mrr=0.463)) == 1


def test_a_guard_dropping_beyond_noise_is_a_regression() -> None:
    assert _mod._compare(
        _now(answerable_discrimination=27.8), _now(answerable_discrimination=20.0)
    ) == 2


def test_a_guard_wobbling_within_noise_is_ignored() -> None:
    assert _mod._compare(
        _now(answerable_discrimination=27.8), _now(answerable_discrimination=26.5)
    ) == 1


def test_corpus_drift_is_named(capsys) -> None:
    """When another repository moved between save and compare, say so.

    The corpus is other people's work and changes without us; a question can
    become answerable because someone pushed a document. That is a real
    external improvement, but it is not the change under test, and crediting
    it silently is the flag-rate-denominator failure all over again.
    """

    before = _now()
    after = _now(
        answerable_total=8,
        corpus_heads={"tukemen-rgb/site": "bbbbbbbbbbbb"},
    )
    assert _mod._compare(before, after) == 0
    out = capsys.readouterr().out
    assert "corpus moved" in out
    assert "aaaaaaaaaaaa -> bbbbbbbbbbbb" in out


def test_a_newly_measured_outcome_counts(capsys) -> None:
    before = _now()
    del before["answerable_paraphrase"]
    assert _mod._compare(before, _now()) == 0
    assert "newly measured" in capsys.readouterr().out


@pytest.mark.parametrize("key", sorted(_mod.METRIC_KEYS))
def test_every_promised_metric_is_judged(key: str) -> None:
    """A name a backlog item can promise must be either outcome or guard here."""

    assert key in _mod._OUTCOME_KEYS or key in _mod._GUARD_KEYS


def test_adding_questions_is_not_bankable(capsys) -> None:
    """A count that rose because the question set grew is not progress.

    Writing an easy question raises `answered` with no product change; if
    that banked as movement, the rational strategy would be to write
    questions instead of fixing retrieval. Same-set improvements only.
    """

    before = _now()
    after = _now(
        answerable_total=9,
        answerable_direct=9,
        scored={"direct": 13, "paraphrase": 7},
    )
    assert _mod._compare(before, after) == 1
    out = capsys.readouterr().out
    assert "question set changed" in out


def test_a_regression_still_fails_across_question_set_changes() -> None:
    """Shrinking or reshaping the set must not launder a real drop."""

    before = _now(answerable_direct=7)
    after = _now(answerable_direct=5, scored={"direct": 9, "paraphrase": 9})
    assert _mod._compare(before, after) == 2


def test_a_better_excerpt_is_movement(capsys) -> None:
    """More citations showing their answer is a product improvement.

    It is the one thing this number exists to reward: same questions answered,
    same ranks, but the operator can now read the answer in the excerpt rather
    than being asked to trust the citation.
    """

    assert _mod._compare(
        _now(excerpt_hits_marker=4), _now(excerpt_hits_marker=6)
    ) == 0
    assert "LOOP_LOG: excerpt_hits_marker 4 -> 6" in capsys.readouterr().out


def test_an_excerpt_count_over_a_changed_denominator_is_not_compared(capsys) -> None:
    """4/7 against 6/9 is not an improvement; it is two different questions.

    The denominator here is `answered`, and four of the five repositories move
    on their own. Without this rule someone else's push could hand this loop a
    completion, and - worse - a retrieval regression that drops hard questions
    would raise the rate it is scored on.
    """

    assert _mod._compare(
        _now(excerpt_hits_marker=4, excerpt_scored=7),
        _now(excerpt_hits_marker=6, excerpt_scored=9),
    ) == 1
    out = capsys.readouterr().out
    assert "excerpt denominator changed" in out
    assert "BETTER" not in out and "WORSE" not in out


def test_a_newly_measured_excerpt_count_is_movement(capsys) -> None:
    """The unmeasurable -> baseline step, same as any other new number."""

    before = _now()
    del before["excerpt_hits_marker"]
    del before["excerpt_scored"]

    assert _mod._compare(before, _now(excerpt_hits_marker=4)) == 0
    assert "excerpt_hits_marker (newly measured) -> 4" in capsys.readouterr().out


def test_guard_drop_across_a_set_change_is_not_a_regression(capsys) -> None:
    """Option (a), CEO direction 2026-08-23: growing the set must be possible.

    Discrimination and MRR are rates over the scored set, so adding harder
    questions lowers them mechanically. Before this rule, C-982 measured
    exactly that: six honest paraphrase additions moved discrimination
    25.9 -> 21.2 and were judged exit 2, so the set could never grow. Across
    a set change only the absolute floors (enforced before _compare) gate;
    the relative guard is not comparable in either direction.
    """

    before = _now()
    after = _now(
        answerable_discrimination=21.2,
        answerable_mrr=0.228,
        scored={"direct": 11, "paraphrase": 13},
    )
    assert _mod._compare(before, after) == 1
    out = capsys.readouterr().out
    assert "absolute floor" in out


def test_guard_drop_on_the_same_set_still_regresses() -> None:
    """The set-change exemption must not leak into same-set runs."""

    assert _mod._compare(
        _now(answerable_discrimination=27.8),
        _now(answerable_discrimination=21.2),
    ) == 2


def test_more_creator_questions_answered_is_movement(capsys) -> None:
    """The number the CEO's direction points at, judged like any other."""

    assert _mod._compare(
        _now(game_production_answered=3), _now(game_production_answered=5)
    ) == 0
    assert "LOOP_LOG: game_production_answered 3 -> 5" in capsys.readouterr().out


def test_a_creator_count_over_a_changed_subset_is_not_compared(capsys) -> None:
    """Filling in coverage is not the same as answering more.

    The creator-facing set is expected to grow as topics are added, and 5/12
    against 3/8 is two different measurements. Comparing them would let
    writing questions read as product progress - the same trap the headline
    counts already refuse.
    """

    assert _mod._compare(
        _now(game_production_answered=3, game_production_scored=8),
        _now(game_production_answered=5, game_production_scored=12),
    ) == 1
    out = capsys.readouterr().out
    assert "game-production question set changed" in out
    assert "BETTER" not in out and "WORSE" not in out
