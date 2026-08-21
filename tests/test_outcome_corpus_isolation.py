"""The outcome measurement must not be able to answer itself.

`src/sidra_ai/evals/outcome_questions.py` states every `answer_marker`
verbatim - it has to, that is what it is for. It is also a `.py` file inside
an allowlisted repository, so the corpus walk picked it up and indexed it.
The retriever then found each marker in the file that declares it and returned
rank 1, and the grounding check passed for the same reason.

Measured against a checkout of this repository alone, that produced
`回答可能率 100.0% / MRR 1.000` with none of the repositories the questions
name present on disk. The number meant to prove SIDRA works on outside
material was scoring the answer key against itself, and it failed in the
direction that looks like success.

`tests/test_outcome_questions.py` already forbids a question from *declaring*
sidra-ai as its repository. That is a different check: it constrains what the
question set says, while these constrain where the evidence is allowed to come
from.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from sidra_ai.evals.outcome_questions import OUTCOME_QUESTIONS
from sidra_ai.retrieval.search import BM25Retriever
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.gate import GatePolicy, SecurityGate

ROOT = Path(__file__).resolve().parents[1]
ANSWER_KEY = "src/sidra_ai/evals/outcome_questions.py"


def _load_script():
    path = ROOT / "scripts" / "measure_outcomes.py"
    spec = importlib.util.spec_from_file_location("measure_outcomes_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script()


def test_the_answer_key_is_excluded_from_the_corpus(script):
    """Indexing the file that lists the answers hands over the answer key."""
    assert (ROOT / ANSWER_KEY).is_file(), "the answer key moved; update this test"

    paths = {rel_path for rel_path, _content in script.iter_files(ROOT)}
    assert ANSWER_KEY not in paths


def test_a_marker_is_not_grounded_by_a_different_repository(script, tmp_path):
    """Evidence has to come from the repository the question is about.

    Otherwise a stray copy of the marker anywhere in the corpus grounds the
    question - which is how all 18 questions were grounded while none of their
    repositories was checked out.
    """
    owner = tmp_path / "owner"
    stranger = tmp_path / "stranger"
    owner.mkdir()
    stranger.mkdir()
    (stranger / "notes.md").write_text("weekly active players", encoding="utf-8")

    targets = [("tukemen-rgb/Fg", owner), ("tukemen-rgb/site", stranger)]

    assert not script.marker_present_in_corpus(
        "weekly active players", "tukemen-rgb/Fg", targets
    )

    (owner / "kpi.md").write_text("weekly active players", encoding="utf-8")
    assert script.marker_present_in_corpus(
        "weekly active players", "tukemen-rgb/Fg", targets
    )


def test_this_repository_alone_answers_none_of_the_questions(script):
    """The regression itself, end to end.

    Before the fix this scored 18/18 at rank 1. Every headline question must
    now come back ungrounded, because the repositories they ask about are not
    here. A run that cannot measure has to say so rather than report a rate.

    The self-grounded questions are the deliberate exception approved on
    2026-08-20: they *are* answered from this repository, which is why they
    are counted on their own line. The assertion is therefore against the
    headline set rather than the whole file - and the point it defends is
    unchanged, because the headline block is what a rate is printed from.
    """
    targets = [("tukemen-rgb/sidra-ai", ROOT)]
    gate = SecurityGate(GatePolicy(), allowed_repositories=["tukemen-rgb/sidra-ai"])
    store = DocumentStore(gate)
    script.ingest(targets, store, gate)

    result = script.measure_answerable(BM25Retriever(store), targets)

    assert result["scored"] == 0, (
        "a question was scored against this repository's own files; "
        "the corpus is answering itself"
    )
    headline = [q for q in OUTCOME_QUESTIONS if not q.self_grounded]
    assert len(result["ungrounded"]) == len(headline)
    assert result["answered"] == 0


def test_an_unmeasurable_run_does_not_print_a_rate(script, capsys, monkeypatch):
    """0/0 rendered as 0.0% reads as a retrieval failure that never happened.

    The distinction matters most to the loop: "0%" invites someone to go
    hunting for a bug in the retriever, when the corpus was simply absent.
    """
    monkeypatch.setattr(sys, "argv", ["measure_outcomes.py", f"tukemen-rgb/sidra-ai={ROOT}"])

    exit_code = script.main()
    report = capsys.readouterr().out

    assert exit_code == 1, "an unmeasurable run must not exit clean"
    assert "回答可能率    測定不能" in report
    assert "回答可能率    0.0%" not in report


def test_a_miss_reports_how_far_the_evidence_was(script, tmp_path) -> None:
    """A bare MISS invites the cheapest hypothesis and hours of wrong work.

    Rank 6 and "not in the top 200" need opposite fixes - reranking versus a
    different notion of similarity - so the report has to distinguish them.
    """
    from sidra_ai.evals.outcome_questions import OutcomeQuestion
    from sidra_ai.retrieval.search import BM25Retriever
    from sidra_ai.retrieval.store import DocumentStore

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "answer.md").write_text(
        "配信の方針について。海外の利用者にも同じ条件で提供する。", encoding="utf-8"
    )
    for index in range(3):
        (repo / f"noise{index}.md").write_text(
            f"無関係な配信ログ {index}。配信の方針とは関係がない。", encoding="utf-8"
        )

    targets = [("tukemen-rgb/site", repo)]
    gate = SecurityGate(GatePolicy(), allowed_repositories=["tukemen-rgb/site"])
    store = DocumentStore(gate)
    script.ingest(targets, store, gate)

    question = OutcomeQuestion(
        name="probe",
        question="海外の利用者にも同じ条件で提供する",
        answer_marker="海外の利用者にも同じ条件で提供する",
        repository="tukemen-rgb/site",
    )
    detail = script.diagnose_miss(BM25Retriever(store), question)

    assert detail["gold_chunks"] >= 1
    assert detail["rank"] == 1
    assert detail["query_terms"] > 0
    assert detail["shared"], "an exact-wording question must share tokens with its answer"


def test_the_overlap_report_only_names_words_the_question_already_contains(
    script, tmp_path
) -> None:
    """The report must not become a way to read indexed documents.

    It prints an intersection, so every token shown is one the asker wrote.
    Anything else would be a content leak wearing a diagnostic's clothes.
    """
    from sidra_ai.evals.outcome_questions import OutcomeQuestion
    from sidra_ai.retrieval.search import BM25Retriever, tokenize
    from sidra_ai.retrieval.store import DocumentStore

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "answer.md").write_text(
        "配信の方針。これは質問には出てこない固有の記述である。", encoding="utf-8"
    )

    targets = [("tukemen-rgb/site", repo)]
    gate = SecurityGate(GatePolicy(), allowed_repositories=["tukemen-rgb/site"])
    store = DocumentStore(gate)
    script.ingest(targets, store, gate)

    question = OutcomeQuestion(
        name="probe",
        question="配信の方針は何ですか",
        answer_marker="配信の方針",
        repository="tukemen-rgb/site",
    )
    detail = script.diagnose_miss(BM25Retriever(store), question)

    question_tokens = set(tokenize(question.question))
    assert set(detail["shared"]) <= question_tokens


def test_a_question_with_no_evidence_reports_no_rank(script, tmp_path) -> None:
    """Nothing to find is not the same as found-but-ranked-badly."""
    from sidra_ai.evals.outcome_questions import OutcomeQuestion
    from sidra_ai.retrieval.search import BM25Retriever
    from sidra_ai.retrieval.store import DocumentStore

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "unrelated.md").write_text("まったく別の話題。", encoding="utf-8")

    targets = [("tukemen-rgb/site", repo)]
    gate = SecurityGate(GatePolicy(), allowed_repositories=["tukemen-rgb/site"])
    store = DocumentStore(gate)
    script.ingest(targets, store, gate)

    question = OutcomeQuestion(
        name="probe",
        question="存在しない答えについて",
        answer_marker="コーパスに無いマーカー",
        repository="tukemen-rgb/site",
    )
    detail = script.diagnose_miss(BM25Retriever(store), question)

    assert detail["gold_chunks"] == 0
    assert detail["rank"] is None
