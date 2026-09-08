"""The index holds one string per distinct term, not one per occurrence.

``run[i:i+2]`` builds a new string every time it is evaluated, so a corpus
tokenized this way used to hold one object per *token* rather than one per
*distinct token*. Measured: 1,440,000 objects for 24 distinct values, and a
32,860-chunk index whose postings weighed 680 MB. Handing back the memo's own
key instead of the argument brought that to 412 MB from 786 MB total, with
the postings holding exactly as many objects as they hold values.

Memory is what limits how large a corpus this can hold - search at that size
is 22 ms, and the process was near a gigabyte - so the sharing is a property
worth pinning rather than a happy accident of the current implementation.

The value-level behaviour is pinned elsewhere (the tokenizer's output is
compared against the previous implementation on the whole corpus). What these
add is identity: same value, same object.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.retrieval import search  # noqa: E402
from sidra_ai.retrieval.search import tokenize  # noqa: E402


def test_the_same_term_from_two_texts_is_one_object() -> None:
    first = tokenize("収益化の方針について書いた文書")
    second = tokenize("別の文書もまた収益化の方針に触れる")

    shared = set(first) & set(second)
    assert shared, "the fixture must share at least one term"
    for term in shared:
        a = next(t for t in first if t == term)
        b = next(t for t in second if t == term)
        assert a is b, f"{term!r} is two objects, so every chunk carries a copy"


def test_repeats_within_one_text_are_one_object() -> None:
    tokens = tokenize("審査の基準。審査の基準。審査の基準。")

    by_value: dict[str, set[int]] = {}
    for token in tokens:
        by_value.setdefault(token, set()).add(id(token))

    assert tokens, "the fixture must produce tokens"
    assert all(len(ids) == 1 for ids in by_value.values())


def test_latin_words_are_shared_too() -> None:
    """Not only CJK: a Latin word repeats across a codebase just as much."""

    first = tokenize("retrieval and ranking notes")
    second = tokenize("more retrieval notes")

    shared = set(first) & set(second)
    assert shared
    for term in shared:
        assert next(t for t in first if t == term) is next(
            t for t in second if t == term
        )


def test_clearing_the_memo_costs_sharing_and_not_correctness() -> None:
    """The cap exists for text we did not write; it must not change answers."""

    text = "収益化の方針と審査の基準"
    before = tokenize(text)
    search._TOKEN_CACHE.clear()
    after = tokenize(text)

    assert before == after
    # New objects after a clear is expected - that is what the cap trades.
    assert all(isinstance(t, str) for t in after)


def test_the_memo_is_bounded() -> None:
    limit = search._TOKEN_CACHE_MAX
    try:
        search._TOKEN_CACHE_MAX = 64
        search._TOKEN_CACHE.clear()
        for i in range(200):
            tokenize(f"語彙{i}番目の断片について")
        assert len(search._TOKEN_CACHE) <= 64
    finally:
        search._TOKEN_CACHE_MAX = limit
        search._TOKEN_CACHE.clear()
