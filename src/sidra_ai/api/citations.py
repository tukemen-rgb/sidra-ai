"""How a cited chunk becomes the excerpt an operator actually sees.

This is one module on purpose. Until now the rule - take the opening of the
chunk, screen it, keep it inside the cap - lived only inside the service, and
anything that wanted to *measure* the excerpt had to re-implement it. A
measurement that re-implements the thing it measures drifts from it silently
and then reports numbers about a program that does not exist, which is the
failure mode this project has already been bitten by once.

So the service calls this, and ``measure_outcomes.py`` calls this, and when
the selection rule changes both move together or neither does.

Choosing the window
-------------------

The opening of a chunk is where an answer *often* is, not where it always is.
Measured over the five repositories, 8 of 10 answered questions had their
answer inside the first ``MAX_CITATION_EXCERPT_CHARS`` characters; the other
two produced a citation that looked like evidence and showed none of it.

So the window moves to where the question is being discussed: candidate
starts are line *and* sentence boundaries (C-1270 - a Japanese paragraph has
no line breaks, so without sentence starts the window could not move at all),
each is scored by how many *distinct* query terms its window contains, and the
best-scoring window wins. A tie among matching windows goes to the latest, so
the window opens on the answering sentence rather than clipping it at the far
edge; with nothing matching at all the fallback is the top, exactly as before.

The query and the document are the only inputs. Selecting the window by
looking for the answer would make every excerpt measurement a tautology - the
excerpt would contain the answer because we went and found it - so the answer
marker is never available here and this module has no idea one exists.
"""

from __future__ import annotations

from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS
from sidra_ai.retrieval.search import tokenize
from sidra_ai.security.output_guard import OutputGuard

#: Never scan more than this many candidate starts in one chunk. Chunks are
#: bounded already, so this is a guard against a pathological document (one
#: enormous line-broken table) costing more than the retrieval that found it.
_MAX_CANDIDATES = 64


def select_excerpt_window(content: str, query: str) -> str:
    """Return the ``MAX_CITATION_EXCERPT_CHARS`` slice most on-topic for ``query``.

    Falls back to the opening of the chunk whenever there is nothing to
    prefer: an empty query, a query whose terms appear nowhere, or a chunk
    that fits inside the cap. That fallback is the previous behaviour, so a
    citation can only become more relevant than it was, never less.
    """

    if len(content) <= MAX_CITATION_EXCERPT_CHARS:
        return content

    terms = set(tokenize(query))
    if not terms:
        return content[:MAX_CITATION_EXCERPT_CHARS]

    best_start = 0
    best_score = -1
    for start in _candidate_starts(content):
        window = content[start : start + MAX_CITATION_EXCERPT_CHARS]
        score = len(terms & set(tokenize(window)))
        # A tie is won by the *latest* window carrying the same evidence.
        # Several windows scoring alike is the normal case - the matched
        # sentence sits inside all of them - and the earliest of those is the
        # one that clips it at the far edge, handing the operator the first
        # half of the line that answered them. The latest instead opens on
        # that line and shows what follows it.
        #
        # Only when something actually matched. With a score of zero every
        # window ties, and "latest" would mean answering a query that appears
        # nowhere with the *end* of the chunk. Nothing to prefer means the
        # opening, which is the documented fallback above.
        if score > best_score or (score == best_score and score > 0):
            best_start, best_score = start, score
    return content[best_start : best_start + MAX_CITATION_EXCERPT_CHARS]


#: A window may open right after one of these, as well as after a newline.
#: Japanese prose runs a paragraph on one line and ends its sentences with 。,
#: so without sentence boundaries the window has a single candidate - the head -
#: and cannot move to the answering sentence (C-1270). Kept to CJK marks: English
#: carries hard line breaks, and ASCII "." would open a window mid-abbreviation.
_SENTENCE_ENDERS = "。！？．"
#: Whitespace after a boundary is skipped so the window opens on the first real
#: character of the next line or sentence, not on the break itself.
_BOUNDARY_SKIP = " \t\n　"


def _candidate_starts(content: str) -> list[int]:
    """Clean window starts: the head of the chunk and the first character of
    each line or sentence, bounded and in order.

    Line and sentence boundaries rather than arbitrary offsets: an excerpt that
    begins mid-sentence costs the operator more than the extra relevance buys.
    A newline begins a line - in Markdown also a heading, bullet or table row -
    and a sentence-ending mark begins the next sentence, which in Japanese prose
    is the only boundary a one-line paragraph offers.

    Starts too close to the end are dropped - a window there would be shorter
    than the cap and would score lower for having less text in it, not for
    being less relevant.
    """

    last_useful_start = len(content) - MAX_CITATION_EXCERPT_CHARS
    starts = [0]
    for index, char in enumerate(content):
        if len(starts) >= _MAX_CANDIDATES:
            break
        if char != "\n" and char not in _SENTENCE_ENDERS:
            continue
        start = index + 1
        while start < len(content) and content[start] in _BOUNDARY_SKIP:
            start += 1
        if start > last_useful_start:
            break
        if start > starts[-1]:
            starts.append(start)
    return starts


def citation_excerpt(
    content: str, output_guard: OutputGuard, query: str = ""
) -> tuple[str, bool]:
    """Return ``(excerpt, withheld)`` for one cited chunk.

    ``withheld`` is true when evidence exists but the output guard refused to
    show it. That is not the same fact as an empty excerpt and the caller has
    to be able to tell them apart: "we are not showing you this" and "there is
    nothing here" read identically once both are the empty string.

    The cap is applied twice - before and after screening - because the guard
    may redact in place and a redaction can be longer than what it replaced.
    """

    excerpt = select_excerpt_window(content, query)
    if not excerpt:
        return "", False
    # C-1264: a window that drops the head or tail of the chunk ends (or starts)
    # abruptly - mid-word for CJK - and read as broken data with no sign it was
    # clipped. Mark each clipped edge with 「…」, detected on the pre-guard window
    # so a redaction cannot confuse the comparison. The cap still holds: the
    # marks' width is taken out of the body, not added on top.
    head_cut = not content.startswith(excerpt)
    tail_cut = not content.endswith(excerpt)
    guarded = output_guard.scan(excerpt)
    if guarded.blocked:
        return "", True
    lead = "…" if head_cut else ""
    trail = "…" if tail_cut else ""
    budget = MAX_CITATION_EXCERPT_CHARS - len(lead) - len(trail)
    return lead + guarded.content[:budget] + trail, False
