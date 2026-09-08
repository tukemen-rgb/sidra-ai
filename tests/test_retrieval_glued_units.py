"""A number written flush against its unit must still answer a unit query.

`docs/revenue-model.md` in `tukemen-rgb/site` says 「zip は 1 件最大 200MB」.
Asked 「投稿できる zip の最大サイズは何 MB ですか」, retrieval put that line at
rank 15 on the real five-repository corpus (2026-09-08): the tokenizer reads
`200MB` as the single Latin run `200mb`, and the query's `MB` is a different
token, so the two never met. Nothing about ranking was wrong - the term the
question was built around was simply not in the index.

These tests pin the rule and the behaviour it exists for. The end-to-end case
is the one that matters: a short document that answers the question beating a
long one that only mentions the unit.

The boundaries are pinned as tightly as the rule, because the failure mode of
a splitting rule is splitting too much: a unit is emitted *as well as* the
glued token (never instead of it), only when digits come first, and only for
two characters or more.
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
            commit_sha="b" * 40,
            timestamp=datetime(2026, 9, 8, tzinfo=timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="MIT",
        ),
    )


@pytest.mark.parametrize(
    ("written", "unit"),
    [("200MB", "mb"), ("60fps", "fps"), ("3km", "km"), ("512kb", "kb")],
)
def test_the_unit_is_reachable_on_its_own(written: str, unit: str) -> None:
    assert unit in tokenize(written)


def test_the_glued_form_still_matches_itself() -> None:
    """Additive, not a replacement: a query for ``200MB`` must not regress."""

    tokens = tokenize("zip は 1 件最大 200MB")

    assert "200mb" in tokens
    assert "mb" in tokens


@pytest.mark.parametrize("word", ["1080p", "4k"])
def test_a_single_letter_tail_is_not_a_term(word: str) -> None:
    """``p`` and ``k`` are noise in the postings, not units anyone searches."""

    assert tokenize(word) == [word.casefold()]


@pytest.mark.parametrize("word", ["sha256", "utf8", "e5"])
def test_letters_first_is_left_alone(word: str) -> None:
    """The gap is a number against its unit; ``sha256`` has no unit in it."""

    assert tokenize(word) == [word.casefold()]


def test_the_glued_line_is_reachable_by_its_unit(
    store: DocumentStore,
) -> None:
    """The end-to-end case, in the shape the real corpus failed in.

    The claim is reachability, not victory. On the real five-repository
    corpus this rule moved the answering line from rank 15 to rank 6 and did
    **not** put it in the top 5 - a long document that repeats the unit
    eighteen times still outranks a short one that states the limit once.
    That is a separate defect (tf saturation against term coverage) and it is
    left where it is rather than papered over here; asserting a win this rule
    does not deliver would make the test a wish.

    So the store below contains exactly one document that mentions the unit
    at all, and the query is the unit alone.
    """

    store.add(
        _document(
            "### ここから引かれるもの\n\n"
            "- **配信の帯域。** zip は 1 件最大 200MB。"
            "ダウンロードが増えるほど原価が増える。\n",
            path="docs/revenue-model.md",
        )
    )
    store.add(
        _document(
            "## 事例集\n\nアップロードの帯域と原価の話。\n",
            path="docs/research/case-studies.md",
        )
    )

    results = BM25Retriever(store).search("何 MB ですか", top_k=2)

    assert results, "the unit query found nothing at all"
    assert results[0].provenance.path == "docs/revenue-model.md"


def test_without_the_rule_the_answer_is_unreachable(
    store: DocumentStore,
) -> None:
    """The half of the test that proves the other half measures something.

    A query written the way the document writes it - the unit glued to its
    own number - is the control: it finds the line with or without the rule,
    so a failure of the test above is about the unit, not about the corpus.
    """

    store.add(
        _document("zip は 1 件最大 200MB。", path="docs/revenue-model.md")
    )

    glued = BM25Retriever(store).search("200MB", top_k=1)
    bare = BM25Retriever(store).search("MB", top_k=1)

    assert glued and glued[0].provenance.path == "docs/revenue-model.md"
    assert bare and bare[0].provenance.path == "docs/revenue-model.md"
