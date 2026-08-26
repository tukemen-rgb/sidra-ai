"""A chunk that matches the shape of a question has not answered it.

Measured 2026-08-26 over the real five-repository index: the chunk that won
"競合はどこですか" contains 競合 zero times. It won on はど/どこ/こで/すか -
the grammar of the sentence - because CJK character bigrams count particles
and endings exactly like content words, and IDF then *rewards* them: question
grammar is rarer than content in a corpus of prose documents. One interview
questionnaire, which is nothing but questions, took first place for a quarter
of a twenty-question set that way.

These tests hold the fix in place from both sides: the questionnaire must not
win, and turning the penalty off must put it back on top. A meter that cannot
detect the defect it was written for is not a meter.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.retrieval import search as search_module
from sidra_ai.retrieval.search import BM25Retriever, is_grammar_term
from sidra_ai.retrieval.store import DocumentStore

REPO = "tukemen-rgb/Fg"

# Nothing but question grammar: the words a questionnaire is made of, and not
# one of the content words any of the questions below are about.
QUESTIONNAIRE = (
    "対象はどこですか。理由はどこですか。時期はどこですか。"
    "きっかけはどこでしたか。感想はどうでしたか。"
)

# The document that actually answers, in one line, with the content word.
ANSWER = "競合は Roblox と Fortnite Creative の二社です。"


def _document(content: str, *, path: str) -> Document:
    return Document(
        content=content,
        provenance=Provenance(
            source="github",
            repository=REPO,
            path=path,
            commit_sha="b" * 40,
            timestamp=datetime(2026, 8, 26, tzinfo=timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="MIT",
        ),
    )


def _corpus(store: DocumentStore) -> BM25Retriever:
    store.add(_document(QUESTIONNAIRE, path="docs/research/interviews.md"))
    store.add(_document(ANSWER, path="docs/research/competitors.md"))
    return BM25Retriever(store)


def test_the_answer_outranks_the_questionnaire(store: DocumentStore) -> None:
    results = _corpus(store).search("競合はどこですか", repositories=[REPO], top_k=2)

    assert results, "the query returned nothing at all"
    assert "競合" in results[0].content, (
        "the top result does not contain the word the question is about: "
        f"{results[0].provenance.path}"
    )


def test_the_defect_returns_when_the_penalty_is_removed(
    store: DocumentStore, monkeypatch
) -> None:
    """Proof that this corpus reproduces the thing being guarded against."""

    monkeypatch.setattr(search_module, "_GRAMMAR_ONLY_WEIGHT", 1.0)
    results = _corpus(store).search("競合はどこですか", repositories=[REPO], top_k=2)

    assert results
    assert "競合" not in results[0].content, (
        "with the penalty disabled the questionnaire no longer wins, so this "
        "test is no longer measuring the defect it was written for"
    )


def test_a_grammar_only_chunk_is_still_returned(store: DocumentStore) -> None:
    """Held down, not dropped.

    Refusing to return anything without a content-word match was measured on
    2026-08-26 and rejected: it removed 3 of 7 wrong answers at the cost of 4
    of 12 correct ones. The penalty is a fraction rather than zero precisely so
    that these chunks keep a non-zero score and stay in the list.
    """

    results = _corpus(store).search("競合はどこですか", repositories=[REPO], top_k=2)

    assert len(results) == 2
    assert all(result.score > 0.0 for result in results)


def test_grammar_in_support_of_content_keeps_its_full_weight(
    store: DocumentStore,
) -> None:
    """The penalty is a property of the chunk, not of the term.

    If grammar terms were simply worth less everywhere, every ranking in the
    corpus would shift. Only chunks that matched nothing but grammar are
    affected, so a chunk that does match content scores the same as it did.
    """

    retriever = _corpus(store)
    with_penalty = retriever.search("競合はどこですか", repositories=[REPO], top_k=2)

    penalised = {r.chunk.chunk_id: r.score for r in with_penalty}
    answer = next(r for r in with_penalty if "競合" in r.content)

    search_module._GRAMMAR_ONLY_WEIGHT, original = 1.0, search_module._GRAMMAR_ONLY_WEIGHT
    try:
        unpenalised = retriever.search("競合はどこですか", repositories=[REPO], top_k=2)
    finally:
        search_module._GRAMMAR_ONLY_WEIGHT = original

    same = next(r for r in unpenalised if r.chunk.chunk_id == answer.chunk.chunk_id)
    assert same.score == penalised[answer.chunk.chunk_id]


def test_which_terms_count_as_grammar() -> None:
    """Crude on purpose - see the docstring on ``is_grammar_term``."""

    assert is_grammar_term("はど")
    assert is_grammar_term("すか")
    assert not is_grammar_term("競合")
    assert not is_grammar_term("合は"), "a bigram straddling a kanji is content"
    assert not is_grammar_term("ロブ"), "katakana is content"
    assert not is_grammar_term("bm25")
