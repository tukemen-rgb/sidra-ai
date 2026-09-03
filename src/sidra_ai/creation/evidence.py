"""What a generator is allowed to build content from.

A ``Fact`` is one retrieved passage plus where it came from. It lives here,
apart from any particular generator, because the router now carries evidence
to whichever generator it calls, and a router that had to import the deck
builder to know what a fact is would depend on every generator that ever
exists.

The type is deliberately thin: text and a source label, both already screened
by the security gate on the way into the index. There is no score, no chunk
id and no document object, because a generator that could see those would be
able to reach back into retrieval, and its output is supposed to be bounded
by exactly what it was handed.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from sidra_ai.retrieval.search import subject_terms, tokenize

#: Anything that looks like a quantity. Deliberately broad - a false positive
#: costs one extra evidence check, a false negative puts an unsourced number
#: in front of a reader, which is the failure this whole path exists to
#: prevent.
NUMBER = re.compile(r"\d[\d,.\s]*\s*(?:%|％|円|万|億|人|件|倍|pt|x)?", re.IGNORECASE)


@dataclass(frozen=True)
class Fact:
    """One retrieved claim and where it came from.

    ``source`` is a repository-and-path label. ``text`` is passage text the
    caller has already taken from an allowed chunk - a generator never reads
    a document itself.
    """

    text: str
    source: str

    def mentions_number(self) -> bool:
        return bool(NUMBER.search(self.text))


@lru_cache(maxsize=1)
def _artifact_terms() -> frozenset[str]:
    """Words that name the *thing being made*, not what it is about.

    Found by reproducing the failure rather than by thinking about it. The
    first version of the filter below kept every jam-recipe passage in a
    weekly-report request, because those passages happened to contain the
    word 「レポート」 - which is a subject term by every measure
    :func:`subject_terms` has, and is also the one word the request was
    guaranteed to share with anything the corpus says about reports.

    The vocabulary is the creation detector's own, so a kind added there
    cannot be forgotten here: whatever names an artifact for the router
    names an artifact for this.
    """

    from sidra_ai.creation.intent import _ARTIFACTS

    return frozenset(
        term
        for words in _ARTIFACTS.values()
        for word in words
        for term in tokenize(word)
    )


def on_topic(request: str, facts: Sequence[Fact]) -> tuple[list[Fact], list[Fact]]:
    """Split retrieved facts into the ones about the request, and the rest.

    C-1201 put a floor under the *answer* path: BM25's CJK bigrams fill
    ``top_k`` on cross-word glue, so a question about the weather came back
    as cited marketing copy. The generators were never given the same
    floor, and a document is where it shows worst - a weekly-report
    request would print jam-making steps under 「わかっていること」, each
    with a source label, which is the shape a reader trusts most.

    The rule is the same one, applied per fact rather than to the batch: a
    fact belongs in the document when it shares at least one subject term
    with the request. A request with no subject terms at all cannot be
    judged, so everything is kept - the existing behaviour, unchanged.

    **Nothing matching is also unjudgeable**, and the filter stands down
    rather than emptying the report. 「進捗レポートを作って」 over this
    repository's own docs is the case that proved it: the evidence a
    progress report is made of (「索引した文書が 482 件ある」) does not
    contain the word 進捗, so a strict reading set every fact aside and
    produced a document of blank headings. The filter's own evidence that
    it understood the request is that *something* matched; without that it
    cannot tell "all of this is off-topic" from "the subject word is simply
    not this corpus's vocabulary", and the failure it exists to stop is a
    mixture, which by definition has a matching half.

    Returns ``(kept, set_aside)``. Both halves matter: the caller says how
    many it put down, because a document quietly shorter than its evidence
    is its own kind of dishonesty.
    """

    wanted = set(subject_terms(request)) - _artifact_terms()
    if not wanted:
        return list(facts), []
    kept, aside = [], []
    for fact in facts:
        (kept if wanted.intersection(tokenize(fact.text)) else aside).append(fact)
    if not kept:
        return list(facts), []
    return kept, aside


__all__ = ["Fact", "NUMBER", "on_topic"]
