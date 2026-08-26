"""A question's grammar must not outrank its subject.

Japanese is tokenized as character bigrams, which splits 「競合はどこですか」
into 競合 / 合は / はど / どこ / こで / すか. Four of those six describe how the
sentence is built, not what it is about - and BM25 cannot tell the difference
on its own, because IDF rewards rarity and an unusual particle collocation is
lexically rare while carrying no topic at all.

Measured on the real 484-document corpus before this was fixed: ``はど``
scored IDF 4.30 against 3.69 for ``競合``, so one interview questionnaire took
first place for a quarter of a 20-question set - competitors, monetisation,
moderation, privacy, the 90-day plan - while the content word appeared **zero
times** in the winning chunk.

These tests pin the two halves of the rule and, more importantly, the
behaviour it exists for: the hijack itself, reproduced end to end.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.retrieval.search import BM25Retriever, tokenize
from sidra_ai.retrieval.store import DocumentStore

REPO = "tukemen-rgb/site"


def _document(content: str, *, path: str) -> Document:
    return Document(
        content=content,
        provenance=Provenance(
            source="github",
            repository=REPO,
            path=path,
            commit_sha="a" * 40,
            timestamp=datetime(2026, 8, 1, tzinfo=timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="MIT",
        ),
    )


@pytest.mark.parametrize(
    "token",
    ["はど", "どこ", "こで", "すか", "たか", "でし", "のは"],
)
def test_hiragana_only_bigrams_are_not_search_terms(token: str) -> None:
    """They are particles and inflections; every Japanese sentence has them."""

    assert token not in tokenize("競合はどこですか。公開したのはいつでしたか")


@pytest.mark.parametrize("token", ["は何", "何で", "が誰", "誰が"])
def test_interrogative_bigrams_are_not_search_terms(token: str) -> None:
    """These carry a kanji, so the hiragana rule alone would let them through.

    ``何で`` measured IDF 6.37 on the real corpus - the highest weight of any
    term in the queries that failed - purely for being a rare way to phrase a
    question.
    """

    assert token not in tokenize("担当は何で、決めたのが誰かを知りたい")


def test_the_subject_of_the_question_survives() -> None:
    """The rule must remove grammar without removing what was asked about."""

    tokens = tokenize("競合はどこですか")

    assert "競合" in tokens
    # Katakana is content in Japanese and must not be caught by the kana rule.
    assert "ゲー" in tokenize("ゲームの話")
    assert "godot" in tokenize("Godot は動きますか")


def test_a_questionnaire_no_longer_outranks_the_document_about_competitors(
    store: DocumentStore,
) -> None:
    """The measured failure, reproduced.

    The decoy shares only the *shape* of the question - "〜はどこでしたか" -
    and contains the word 競合 nowhere. Before the fix it won on はど/どこ/こで
    /すか alone.
    """

    store.add(
        _document(
            "質問票 v1。最近ゲームを公開したのはいつ・どこでしたか。"
            "その公開先はどこで決めましたか。どこで詰まりましたか。",
            path="docs/research/interviews.md",
        )
    )
    store.add(
        _document(
            "競合の整理。unityroom と itch.io を競合として扱う。"
            "競合ごとの審査の有無と対応エンジンを並べた。",
            path="docs/competitive-analysis.md",
        )
    )

    results = BM25Retriever(store).search("競合はどこですか", top_k=2)

    assert results, "the query must still retrieve something"
    assert results[0].chunk.provenance.path == "docs/competitive-analysis.md"


def test_a_query_that_is_only_grammar_retrieves_nothing(store: DocumentStore) -> None:
    """No subject means no evidence, rather than the grammatically nearest chunk."""

    store.add(_document("競合の整理。unityroom を競合として扱う。", path="docs/x.md"))

    assert BM25Retriever(store).search("これはどうですか", top_k=5) == []
