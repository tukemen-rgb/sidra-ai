"""The owner's questions, and the reasons this set can be trusted.

The 2026-08-26 measurement was lost because the questions lived in one
session's memory. Committing them fixes that; keeping them honest is a
separate problem, and these tests are that half. Three ways a question set
quietly stops measuring anything:

* it is padded, so the count goes up without more being asked;
* the question that fails is deleted, so the rate goes up without anything
  improving;
* it is written after reading the corpus, choosing questions already known to
  pass.

The first two are checked directly. The third cannot be checked by a test at
all - only recorded - so what is checked is its fingerprint: a set chosen to
pass would contain no question the corpus cannot answer, and this one does.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from sidra_ai.evals.boss_questions import (
    BOSS_QUESTIONS,
    REPOSITORIES,
    BossQuestion,
    grounded,
    headline,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Registered before execution: the dataclasses in these scripts look
    # themselves up in sys.modules while being defined.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def judge():
    return _load("check_boss_questions_under_test", "scripts/check_boss_questions.py")


# ------------------------------------------------------------------- the set


def test_twenty_questions_are_committed() -> None:
    assert len(BOSS_QUESTIONS) == 20


def test_no_question_is_asked_twice() -> None:
    """Padding a set with near-copies raises the count and measures nothing."""

    assert len({q.name for q in BOSS_QUESTIONS}) == 20
    assert len({q.question for q in BOSS_QUESTIONS}) == 20


def test_every_grounded_question_points_at_an_allowlisted_repository() -> None:
    for question in grounded():
        assert question.repository in REPOSITORIES, question.name
        assert len(question.answer_marker) >= 4, question.name


def test_a_question_the_corpus_cannot_answer_is_kept() -> None:
    """Deleting it would raise the rate while answering nothing.

    It is also the only visible evidence about how the set was written: a set
    assembled from questions already known to pass would not contain one.
    """

    unanswerable = [q for q in BOSS_QUESTIONS if q.answer_marker is None]

    assert unanswerable, (
        "every question in the set is answerable by the corpus, which is what "
        "a set tuned to score well looks like"
    )


def test_self_grounded_questions_stay_out_of_the_headline() -> None:
    """Scoring our own prose is the inside number the set exists to escape."""

    assert any(q.self_grounded for q in grounded())
    assert not any(q.self_grounded for q in headline())
    assert len(headline()) < len(grounded())


# ---------------------------------------------------------------- the judge


def test_a_fall_in_answered_is_a_regression(judge) -> None:
    verdict, lines = judge._compare(
        {"boss_q_answered": 5, "boss_q_wrong_repository": 2,
         "boss_q_scoreable": 18, "denominator": 18},
        {"boss_q_answered": 4, "boss_q_wrong_repository": 2,
         "boss_q_scoreable": 18, "denominator": 18},
    )

    assert verdict == judge.EXIT_REGRESSED
    assert any("boss_q_answered" in line for line in lines)


def test_more_confident_wrong_answers_is_a_regression(judge) -> None:
    """C-1009's failure: not silence, but the wrong repository answering.

    This must fail even while the headline improves, which is the only reason
    the two numbers are counted apart.
    """

    verdict, _ = judge._compare(
        {"boss_q_answered": 5, "boss_q_wrong_repository": 2,
         "boss_q_scoreable": 18, "denominator": 18},
        {"boss_q_answered": 6, "boss_q_wrong_repository": 4,
         "boss_q_scoreable": 18, "denominator": 18},
    )

    assert verdict == judge.EXIT_REGRESSED


def test_a_changed_question_set_cannot_be_compared(judge) -> None:
    verdict, lines = judge._compare(
        {"boss_q_answered": 5, "denominator": 18},
        {"boss_q_answered": 9, "boss_q_wrong_repository": 0,
         "boss_q_scoreable": 12, "denominator": 12},
    )

    assert verdict == judge.EXIT_CANNOT_JUDGE
    assert any("question set changed" in line for line in lines)


def test_a_semantic_run_cannot_be_compared_with_a_lexical_baseline(judge) -> None:
    """Two retrievers are two products, and the difference dwarfs a code change.

    Measured 2026-08-27: the same twenty questions score 1/18 answered under
    bm25 and 2/18 under bm25 + a local embedding model. Read as a comparison
    it would look like a change to the code under test doubling the rate.
    """

    verdict, lines = judge._compare(
        {"boss_q_answered": 1, "boss_q_wrong_repository": 1,
         "boss_q_scoreable": 18, "denominator": 18, "retriever": "bm25"},
        {"boss_q_answered": 2, "boss_q_wrong_repository": 2,
         "boss_q_scoreable": 18, "denominator": 18,
         "retriever": "bm25 + sentence-transformers"},
    )

    assert verdict == judge.EXIT_CANNOT_JUDGE
    assert any("retriever changed" in line for line in lines)


def test_standing_still_is_not_progress(judge) -> None:
    same = {"boss_q_answered": 5, "boss_q_wrong_repository": 2,
            "boss_q_scoreable": 18, "denominator": 18}

    verdict, _ = judge._compare(same, dict(same))

    assert verdict == judge.EXIT_NO_MOVEMENT


# ------------------------------------------------------------- the meter


@pytest.fixture(scope="module")
def metrics():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import product_metrics

    return product_metrics


def test_padding_the_set_does_not_raise_the_count(metrics, monkeypatch) -> None:
    """The number is "questions that can be re-scored", not "lines in a file"."""

    import sidra_ai.evals.boss_questions as module

    padded = (
        BossQuestion(name="real", question="競合はどこですか", topic="競合",
                     answer_marker="ふりーむ！", repository="tukemen-rgb/site"),
        BossQuestion(name="empty", question="?", topic="pad"),
        BossQuestion(name="dupe", question="競合はどこですか", topic="pad",
                     answer_marker="ふりーむ！", repository="tukemen-rgb/site"),
        BossQuestion(name="stub", question="これは長さだけある質問です", topic="pad",
                     answer_marker="あ", repository="tukemen-rgb/site"),
        BossQuestion(name="outside", question="よそのリポジトリの話ですか", topic="pad",
                     answer_marker="どこかの一節", repository="tukemen-rgb/elsewhere"),
    )
    monkeypatch.setattr(module, "BOSS_QUESTIONS", padded)

    collector = metrics.Collector()
    metrics.measure_boss_questions(collector)
    runnable = next(
        m for m in collector.metrics if m.key == "boss_questions_runnable"
    )

    assert runnable.value == 1.0, runnable.detail


def test_the_real_set_is_entirely_runnable(metrics) -> None:
    collector = metrics.Collector()
    metrics.measure_boss_questions(collector)
    runnable = next(
        m for m in collector.metrics if m.key == "boss_questions_runnable"
    )

    assert runnable.value == float(len(BOSS_QUESTIONS)), runnable.detail
