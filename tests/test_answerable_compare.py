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
