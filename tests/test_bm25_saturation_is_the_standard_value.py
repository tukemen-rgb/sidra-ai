"""BM25's term-frequency saturation sits at the value the field defaults to.

``k1`` decides how much a *repeated* word is worth. High values keep paying for
the fifth occurrence of one term; low values saturate quickly, so a chunk that
matches more of the question outranks one that repeats part of it.

This project ran 1.5 with nothing recorded about where that came from. Lucene
and Elasticsearch default to 1.2, so 1.5 was an outlier above the standard
range rather than a measured choice. The change is to the standard value, and
the measurement's job was only to confirm that standard value is not worse
here - which is a different thing from searching our own 38 questions for an
optimum and adopting whatever won.

Measured over the five repositories (2026-09-08, C-1163):

    BM25 alone        1.5: 15/38  direct 13  para 2  disc +0.3  MRR 0.293
                      1.2: 16/38  direct 13  para 3  disc +0.3  MRR 0.302
    with the reranker 1.5: 18/38  direct 13  para 5  disc +0.2  MRR 0.349
                      1.2: 18/38  direct 13  para 5  disc +0.2  MRR 0.353

0.6, 0.9 and 1.2 all read identically, and 2.0 is worse on every axis - a
broad plateau with a bad end, which is what a real effect looks like rather
than a tie-break that happened to land well.

**What it did not do.** The sweep was motivated by five direct-wording
questions whose answering chunk sits at lexical rank 11 to 130, beaten by long
generated logs repeating one query word - precisely what lower saturation
should fix. It fixed none of them, at any value. So the gain above is real but
unexplained by that diagnosis, and the five remain an open finding rather than
a solved one.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sidra_ai.retrieval.search import BM25Retriever  # noqa: E402

#: What Lucene and Elasticsearch use. Changing this is changing what the
#: product ranks by, so it belongs in a test rather than only in a default.
STANDARD_K1 = 1.2
STANDARD_B = 0.75


def test_the_default_is_the_standard_saturation() -> None:
    import inspect

    signature = inspect.signature(BM25Retriever.__init__)
    assert signature.parameters["k1"].default == STANDARD_K1
    assert signature.parameters["b"].default == STANDARD_B


def test_repetition_saturates_rather_than_accumulating() -> None:
    """The property k1 exists for, checked by arithmetic rather than by trust.

    One term seen five times must be worth less than five times one sighting -
    otherwise a long log that repeats a word beats a chunk that answers.
    """

    k1, b = STANDARD_K1, STANDARD_B

    def contribution(frequency: float, length: float = 1.0) -> float:
        denominator = frequency + k1 * (1 - b + b * length)
        return frequency * (k1 + 1) / denominator

    once = contribution(1)
    five = contribution(5)

    assert five > once, "more occurrences must still be worth more"
    assert five < 5 * once, "the fifth occurrence is being paid in full"
    # And the saturation has to be strong enough to matter: five sightings of
    # one word must not outweigh a chunk matching three different words.
    assert five < 3 * once, (
        f"five repeats score {five:.3f} against {3 * once:.3f} for three "
        "distinct matches; repetition still beats coverage"
    )


def test_a_higher_value_is_a_deliberate_choice_not_a_default() -> None:
    """The old value is still reachable - what changed is what you get free."""

    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, SecurityGate

    store = DocumentStore(SecurityGate(GatePolicy(), allowed_repositories=[]))

    assert BM25Retriever(store).k1 == STANDARD_K1
    assert BM25Retriever(store, k1=1.5).k1 == 1.5
