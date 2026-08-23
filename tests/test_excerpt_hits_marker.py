"""The excerpt an operator is shown has to contain the answer.

``answerable`` stops one step short of the operator. It says the answering
chunk came back in the top-k; the citation then shows the first
``MAX_CITATION_EXCERPT_CHARS`` characters of that chunk, and a chunk is much
longer than that. An answer sitting past the cap produces a citation that
looks like evidence and proves nothing, which is the exact failure citations
were added to prevent.

``excerpt_hits_marker`` measures that gap. These tests hold the three
properties that make the number worth reading:

* it scores the text the product would really show - same cap, same output
  guard - rather than a re-implementation that can drift from it;
* its denominator is answered questions, so a retrieval regression cannot
  raise the rate by removing the questions it was failing;
* the marker is used for scoring only. A window chosen by searching for the
  marker would be marking our own exam, so the excerpt is whatever the API
  would have shown for that query and nothing more.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from sidra_ai.api.citations import citation_excerpt
from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS
from sidra_ai.api.service import SidraService
from sidra_ai.evals.outcome_questions import OutcomeQuestion
from sidra_ai.security.output_guard import OutputGuard

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_measure_outcomes():
    spec = importlib.util.spec_from_file_location(
        "measure_outcomes_excerpt_under_test",
        REPO_ROOT / "scripts" / "measure_outcomes.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mo():
    return _load_measure_outcomes()


NEAR_MARKER = "答えはこの一文の中にある固有の言い回しである"
FAR_MARKER = "答えは長い前置きのうしろに置かれた固有の言い回しである"

# Long enough that the marker planted after it falls outside the excerpt cap.
PADDING = "前置きの段落がここに続く。" * 40


def _corpus(tmp_path: Path):
    """One repository, two documents: one answers early, one answers late."""

    repo = tmp_path / "outside"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "near.md").write_text(
        f"# 近い方\n\n近接の質問について。{NEAR_MARKER}\n",
        encoding="utf-8",
    )
    (repo / "docs" / "far.md").write_text(
        f"# 遠い方\n\n遠隔の質問について。{PADDING}\n\n{FAR_MARKER}\n",
        encoding="utf-8",
    )
    return [("other/outside", repo)]


NEAR_QUESTION = OutcomeQuestion(
    name="fixture-near",
    question="近接の質問について教えてください",
    answer_marker=NEAR_MARKER,
    repository="other/outside",
)

FAR_QUESTION = OutcomeQuestion(
    name="fixture-far",
    question="遠隔の質問について教えてください",
    answer_marker=FAR_MARKER,
    repository="other/outside",
)


def _measure(mo, questions, targets):
    original = mo.OUTCOME_QUESTIONS
    mo.OUTCOME_QUESTIONS = tuple(questions)
    try:
        gate = mo.SecurityGate(
            mo.GatePolicy(), allowed_repositories=[name for name, _ in targets]
        )
        store = mo.DocumentStore(gate)
        mo.ingest(targets, store, gate)
        return mo.measure_answerable(mo.BM25Retriever(store), targets)
    finally:
        mo.OUTCOME_QUESTIONS = original


def test_an_answer_inside_the_cap_counts_as_shown(mo, tmp_path) -> None:
    result = _measure(mo, [NEAR_QUESTION], _corpus(tmp_path))

    assert result["answered"] == 1, "fixture broken: the near question must be answered"
    excerpt = result["excerpt"]
    assert excerpt["answered"] == 1
    assert excerpt["shows_marker"] == 1
    assert excerpt["rate"] == 1.0
    assert excerpt["misses"] == []


def test_an_answer_past_the_cap_is_answered_but_not_shown(mo, tmp_path) -> None:
    """The whole point of the number: these two cases must not look alike.

    Both questions retrieve their evidence, so ``answerable`` scores them
    identically. Only the excerpt tally can tell the operator that one of the
    citations does not actually show the answer.
    """

    result = _measure(mo, [FAR_QUESTION], _corpus(tmp_path))

    assert result["answered"] == 1
    excerpt = result["excerpt"]
    assert excerpt["answered"] == 1
    assert excerpt["shows_marker"] == 0
    assert excerpt["misses"] == ["fixture-far"]


def test_the_denominator_is_answered_questions_only(mo, tmp_path) -> None:
    """A question whose evidence never came back has no excerpt to judge.

    Counting misses in the denominator would make this rate movable by
    retrieval, and counting them as failures would punish the excerpt for a
    problem it cannot fix.
    """

    unanswerable = OutcomeQuestion(
        name="fixture-unanswerable",
        question="まったく無関係の話題についての質問",
        answer_marker=NEAR_MARKER,
        repository="other/outside",
    )
    result = _measure(mo, [NEAR_QUESTION, unanswerable], _corpus(tmp_path))

    hits = [row for row in result["rows"] if row["status"] == "hit"]
    assert result["excerpt"]["answered"] == len(hits)


def test_the_measurement_scores_what_the_service_would_show(mo, tmp_path) -> None:
    """Guard against the measurement drifting from the product.

    If the service ever selects its excerpt differently - a different window,
    a different cap - and this measurement keeps taking the opening of the
    chunk, the reported rate becomes a number about a program nobody runs.
    Both sides go through ``citation_excerpt``; this proves the service still
    does.
    """

    class _Chunk:
        content = "先頭の一文。" + "本文が続く。" * 60

    # Built without __init__ on purpose: this test is about the excerpt rule,
    # not about wiring a store, a retriever and a model to reach it.
    service = SidraService.__new__(SidraService)
    service.output_guard = OutputGuard()

    citations = [{"label": "S1"}]
    service._attach_excerpts(citations, [_Chunk()])

    expected, withheld = citation_excerpt(_Chunk.content, OutputGuard())
    assert not withheld
    assert citations[0]["excerpt"] == expected
    assert len(citations[0]["excerpt"]) <= MAX_CITATION_EXCERPT_CHARS


def test_a_withheld_excerpt_is_not_counted_as_shown(mo) -> None:
    """A blocked excerpt shows the operator nothing, marker or not.

    Scoring it as a hit because the marker was in the chunk would report
    evidence the operator was explicitly refused.
    """

    rows = [
        {
            "name": "withheld",
            "status": "hit",
            "excerpt_shows_marker": False,
            "excerpt_withheld": True,
        },
        {
            "name": "shown",
            "status": "hit",
            "excerpt_shows_marker": True,
            "excerpt_withheld": False,
        },
        {"name": "missed", "status": "miss"},
    ]

    tally = mo._tally_excerpts(rows)

    assert tally == {
        "answered": 2,
        "shows_marker": 1,
        "rate": 0.5,
        "withheld": 1,
        "misses": ["withheld"],
    }


# --- window selection (C-983) ------------------------------------------------
#
# The excerpt used to be the opening of the chunk, full stop. Two of the ten
# answered questions had their answer past the cap, so the citation showed
# none of it. These tests hold the rule that replaced it: move the window to
# where the question is discussed, using nothing but the query and the
# document.

LONG_PREAMBLE = "\n".join(f"前置きの行がここに続く{i}。" for i in range(30))
ANSWER_LINE = "順位付けの文化については、完成度で人を落とさないと決めている。"


def test_the_window_moves_to_where_the_query_is_discussed() -> None:
    from sidra_ai.api.citations import select_excerpt_window

    content = f"{LONG_PREAMBLE}\n{ANSWER_LINE}\n{LONG_PREAMBLE}"

    window = select_excerpt_window(content, "順位付けの文化はどうなっていますか")

    assert ANSWER_LINE in window
    assert len(window) <= MAX_CITATION_EXCERPT_CHARS


def test_a_query_with_nothing_in_common_still_opens_at_the_top() -> None:
    """The fallback is the old behaviour, so this can only add relevance.

    A window chosen at random when nothing matches would make citations worse
    than they were for exactly the questions retrieval is already failing.
    """

    from sidra_ai.api.citations import select_excerpt_window

    content = f"{LONG_PREAMBLE}\n{ANSWER_LINE}"

    assert select_excerpt_window(content, "") == content[:MAX_CITATION_EXCERPT_CHARS]
    assert select_excerpt_window(content, "zzz qqq") == (
        content[:MAX_CITATION_EXCERPT_CHARS]
    )


def test_the_window_starts_on_a_line_boundary() -> None:
    """An excerpt that opens mid-sentence costs more than the relevance buys."""

    from sidra_ai.api.citations import select_excerpt_window

    content = f"{LONG_PREAMBLE}\n{ANSWER_LINE}\n{LONG_PREAMBLE}"

    window = select_excerpt_window(content, "順位付けの文化はどうなっていますか")
    start = content.index(window)

    assert start == 0 or content[start - 1] == "\n"


def test_a_chunk_inside_the_cap_is_shown_whole() -> None:
    from sidra_ai.api.citations import select_excerpt_window

    content = "短い章。" + ANSWER_LINE

    assert select_excerpt_window(content, "順位付け") == content


def test_selection_depends_on_the_query_and_the_document_only() -> None:
    """The answer marker is not an input, and cannot become one by accident.

    ``select_excerpt_window`` takes two arguments. If a future change wants to
    pass the marker in to "improve" the rate, it has to change this signature
    and this test - which is the point: an excerpt chosen by looking for the
    answer would make ``excerpt_hits_marker`` measure nothing at all.
    """

    import inspect

    from sidra_ai.api.citations import select_excerpt_window

    assert list(inspect.signature(select_excerpt_window).parameters) == [
        "content",
        "query",
    ]
