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


#: Markdown decoration inside an excerpt window. The corpus is Markdown, so
#: a 200-character window lands mid-document and drags ``##``, ``**`` and
#: ``>`` into slide bullets as literal characters (C-1212). Only decoration
#: is removed - the words are the evidence and must survive unchanged.
_MD_HEADING = re.compile(r"(?:(?<=\s)|^)#{1,6}\s+")
_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_MD_EMPHASIS = re.compile(r"(?<![\w*])\*([^*\s][^*]*)\*(?![\w*])")
_MD_CODE = re.compile(r"`([^`]+)`")
_MD_QUOTE = re.compile(r"(?:(?<=\s)|^)>\s?")
#: A bullet at the start of a line, with or without a task checkbox. Only
#: line-anchored so a mid-sentence dash (「令和 - 平成」) is never touched;
#: applied before whitespace collapse, while line starts still exist (C-1216).
_MD_LIST = re.compile(r"(?m)^[ \t]*[-*+][ \t]+(?:\[[ xX]\][ \t]+)?")

#: Git/AI commit-message trailers. Commits are ~43% of the indexed corpus and
#: every one carries these lines; the echo lead extractor pulled them in as
#: content, so an answer about a commit ended 「…方針を維持。 Co-Authored-By:
#: Claude … Claude-Session: https://…」 - git plumbing shown as substance
#: (C-1221). An allowlist of the actual trailer tokens, not a general
#: 「Word: value」 rule, so content lines like 「TODO:」「影響:」 are left alone.
#: Line-anchored and applied before whitespace collapse, while lines still
#: exist; the raw citation excerpt does not go through here, so review keeps
#: the verbatim message.
_TRAILER = re.compile(
    r"(?im)^[ \t]*(?:co-authored-by|signed-off-by|claude-session|reviewed-by"
    r"|acked-by|tested-by|helped-by|reported-by|suggested-by|cc)[ \t]*:.*$"
)


def plain_text(text: str) -> str:
    """Strip Markdown decoration from an excerpt, keeping every word.

    Heading hashes, bold/emphasis stars, inline backticks and blockquote
    markers become plain prose; anything ambiguous (list numbers, stray
    asterisks in code-like text) is left alone, because dropping a real
    character from quoted evidence is worse than showing one marker.

    Known git/AI commit-message trailer lines (Co-Authored-By, Claude-Session
    and the like) are dropped too: they are plumbing, not content, and the
    corpus is nearly half commits (C-1221). The removal is an allowlist of
    real trailer tokens, so a content line that happens to start 「TODO:」 or
    「影響:」 survives.
    """

    text = _TRAILER.sub("", text)
    text = _MD_LIST.sub("", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_BOLD.sub(r"\1", text)
    text = _MD_EMPHASIS.sub(r"\1", text)
    text = _MD_CODE.sub(r"\1", text)
    text = _MD_QUOTE.sub("", text)
    return " ".join(text.split())


#: Sentence terminators for :func:`whole_sentences`, Japanese and Latin.
#: An ASCII dot counts only when a word character does not follow it: the
#: dots inside 「revenue-model.md」 and 「3.5」 are spelling, and cutting at
#: one ends a bullet mid-filename (C-1217).
_SENTENCE_END = re.compile(r"[。．!?！？]|\.(?!\w)")

#: Below this many characters, a trimmed excerpt says less than a dangling
#: one: 「掲載は 21,907 件。」 alone can carry a claim, but trimming a
#: 200-character window down to its first ten characters throws away the
#: evidence to polish the punctuation.
_MIN_TRIMMED = 50


def whole_sentences(text: str) -> str:
    """Cut a generator-bound excerpt back to its last complete sentence.

    The excerpt window starts at a line boundary by design but ends at a
    hard character cap, so slide bullets used to end mid-word (「…予約投」,
    C-1213). Text with no terminator, or whose last terminator sits too
    close to the head, is returned unchanged - a fragment with content
    beats an empty polish. Never widens the cap; it only trims.
    """

    last = None
    for match in _SENTENCE_END.finditer(text):
        last = match
    if last is None or last.end() < _MIN_TRIMMED:
        return text
    return text[: last.end()].rstrip()


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
