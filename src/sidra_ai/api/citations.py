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
no line breaks, so without sentence starts the window could not move at all;
C-1280 - an English Markdown paragraph is one logical line too, so ASCII "."
is a boundary as well, guarded so an abbreviation or decimal is not one),
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

import re

from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS
from sidra_ai.retrieval.search import tokenize
from sidra_ai.security.output_guard import OutputGuard

#: Never scan more than this many candidate starts in one chunk. Chunks are
#: bounded already, so this is a guard against a pathological document (one
#: enormous line-broken table) costing more than the retrieval that found it.
_MAX_CANDIDATES = 64


def select_excerpt_window(content: str, query: str) -> str:
    """The window itself. See :func:`select_excerpt_span` for how it is chosen."""

    return select_excerpt_span(content, query)[1]


def select_excerpt_span(
    content: str, query: str, *, clean_head: bool = False
) -> tuple[int, str]:
    """Return ``(start, window)``: the ``MAX_CITATION_EXCERPT_CHARS`` slice most
    on-topic for ``query``, and where in ``content`` it begins.

    Falls back to the opening of the chunk whenever there is nothing to
    prefer: an empty query, a query whose terms appear nowhere, or a chunk
    that fits inside the cap. That fallback is the previous behaviour, so a
    citation can only become more relevant than it was, never less.

    ``clean_head`` is the generator's mode (C-1534); see
    :func:`_advance_past_a_half_sentence`.
    """

    if len(content) <= MAX_CITATION_EXCERPT_CHARS:
        return 0, content

    terms = set(tokenize(query))
    if not terms:
        return 0, content[:MAX_CITATION_EXCERPT_CHARS]

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
    if clean_head:
        best_start = _advance_past_a_half_sentence(content, best_start, terms)
    return best_start, content[best_start : best_start + MAX_CITATION_EXCERPT_CHARS]


#: A window may open right after one of these, as well as after a newline.
#: Japanese prose runs a paragraph on one line and ends its sentences with 。,
#: so without sentence boundaries the window has a single candidate - the head -
#: and cannot move to the answering sentence (C-1270).
_SENTENCE_ENDERS = "。！？．"
#: Digits (half- and full-width) for the mid-number tail guard (C-1849), and the
#: run a partial number is trimmed back over - digits plus the in-number group
#: separators. A trailing 「,」/「.」 left after the digits go is part of the number
#: and comes off too; a sentence-ending 「。」 (not in the set) never does.
_DIGITS = frozenset("0123456789０１２３４５６７８９")
_NUMBER_TAIL = "0123456789０１２３４５６７８９,，.．"
#: Whitespace after a boundary is skipped so the window opens on the first real
#: character of the next line or sentence, not on the break itself.
_BOUNDARY_SKIP = " \t\n　"


def _ascii_period_ends_sentence(content: str, index: int) -> bool:
    """Is the ASCII 「.」 at ``index`` a sentence end worth opening a window on?

    C-1280: English prose runs a paragraph on one line just as Japanese does, but
    it ends sentences with ASCII 「.」, which was left out of ``_SENTENCE_ENDERS``
    for fear of opening a window mid-abbreviation. So an English single-line
    paragraph offered a single candidate - the head - and the excerpt could not
    move to the answering sentence, the same failure C-1270 fixed for Japanese.

    A bare 「.」 is too ambiguous to trust, so a period counts only with the shape
    a real sentence break has and an abbreviation does not:

    * the character *before* it is a lowercase letter or a digit - which rejects
      an acronym ending a sentence (「TLS.」) and a person's initial (「J. Doe」),
      the readings most likely to be a false break; and
    * it is followed by whitespace and then an uppercase letter - the start of
      the next sentence - which rejects a decimal (「3.14」) and a period glued to
      the next word.

    The window never opens *inside* the token: the start is taken past the period
    and its trailing whitespace, so even a surviving abbreviation (「e.g. The」)
    opens cleanly on the capitalised word, not on 「g.」. An acronym-ended
    sentence is simply not offered as a start - strictly better than the head-only
    behaviour it replaces, and safe.
    """

    prev = content[index - 1] if index > 0 else ""
    if not (prev.isascii() and (prev.islower() or prev.isdigit())):
        return False
    after = index + 1
    if after >= len(content) or content[after] not in _BOUNDARY_SKIP:
        return False
    while after < len(content) and content[after] in _BOUNDARY_SKIP:
        after += 1
    return after < len(content) and "A" <= content[after] <= "Z"


def _candidate_starts(content: str) -> list[int]:
    """Clean window starts: the head of the chunk and the first character of
    each line or sentence, bounded and in order.

    Line and sentence boundaries rather than arbitrary offsets: an excerpt that
    begins mid-sentence costs the operator more than the extra relevance buys.
    A newline begins a line - in Markdown also a heading, bullet or table row -
    and a sentence-ending mark begins the next sentence, which in Japanese prose
    is the only boundary a one-line paragraph offers.

    A boundary in the last ``MAX_CITATION_EXCERPT_CHARS`` is offered too, not
    dropped (C-1475). The window it yields is shorter than the cap, but scoring
    counts *distinct* matched query terms, so a short window that holds the whole
    answering sentence never scores below an earlier window that clips it. The
    old cutoff instead left the tail of every chunk un-openable, so an answer
    written there - a conclusion, a value, a 「…に設定されている」 - was shown only
    as its first half, the exact failure C-1270's tie-break exists to prevent.
    """

    starts = [0]
    for index, char in enumerate(content):
        if len(starts) >= _MAX_CANDIDATES:
            break
        if char == "\n" or char in _SENTENCE_ENDERS:
            pass
        elif char == "." and _ascii_period_ends_sentence(content, index):
            pass
        else:
            continue
        start = index + 1
        while start < len(content) and content[start] in _BOUNDARY_SKIP:
            start += 1
        if start >= len(content):
            break
        if start > starts[-1]:
            starts.append(start)
    return starts


#: A line opening with one of these starts a new block, so the window opens on a
#: new thought even though the character before it is not a sentence end: a
#: heading, a bullet, an ordered item, a quote, a table row.
_BLOCK_OPENER = re.compile(r"(?:#{1,6}\s|[-*+>|]|\d+[.)]\s)")

#: Characters skipped when looking *back* for the end of the previous sentence.
_LOOK_BACK_SKIP = " \t\n\u3000"


def opens_cleanly(content: str, start: int) -> bool:
    """Does a window opening at ``start`` begin where a reader would begin?

    The excerpt window already opens only at line and sentence boundaries
    (C-1270/C-1280), and measured over the five repositories that is nearly
    always a readable place: of the 20 windows four generated reports were
    built from, 19 opened at a sentence end, a heading, a list item, a table
    row or a paragraph break. One did not, and the difference matters to the
    reader rather than to the retriever - 「あって、システムや方針の指示を
    上書きできない。」 is the back half of a sentence whose front half is on
    the previous line, because this corpus hard-wraps Japanese prose and a
    wrap point is a newline like any other.

    Clean means one of:

    * the chunk's own head - nothing was cut, so nothing is broken;
    * the previous non-space character ends a sentence;
    * the line the window opens on begins a Markdown block; or
    * the previous line is blank, so this is a new paragraph.

    Anything else is the middle of a sentence.
    """

    if start <= 0:
        return True
    before = content[:start]
    stripped = before.rstrip(_LOOK_BACK_SKIP)
    if not stripped:
        return True
    last = stripped[-1]
    if last in _SENTENCE_ENDERS:
        return True
    if last == "." and _ascii_period_ends_sentence(content, len(stripped) - 1):
        return True
    # Line starts only from here: mid-line the question does not arise.
    if not before.rstrip(" \t\u3000").endswith("\n"):
        return False
    if _BLOCK_OPENER.match(content[start:]):
        return True
    lines = before.rstrip(" \t\u3000").split("\n")
    return len(lines) >= 2 and not lines[-2].strip()


#: A head trim must leave at least this much window. Borrowed from the tail
#: rule's ``_MIN_TRIMMED``: below this a trimmed excerpt says less than a
#: dangling one, and the point of the excerpt is the evidence, not the
#: punctuation.
_MIN_ADVANCED = 50


def _advance_past_a_half_sentence(content: str, start: int, terms: set[str]) -> int:
    """Move a mid-sentence window start forward to the next clean one.

    C-1534: a report bullet is the president's paste-into-a-deck surface, and a
    fact that begins in the middle of a sentence reads as broken even when it
    is correct. The tail of a generator-bound excerpt is already cut back to
    the last whole sentence (``whole_sentences``, C-1213); this is the same
    rule at the other end.

    Two things hold it back, both measured rather than assumed:

    * it never costs evidence. The advanced window must still carry every
      query term the chosen window matched, and still be worth reading
      (``_MIN_ADVANCED``). A window that cannot be advanced on those terms is
      left where it is - and then the 「…」 mark is what says so.
    * it only runs for the generator (``clean_head``). The /v1/chat citation
      excerpt keeps its window exactly as it was, because there 「…」 is the
      operator's sign that they are looking at a slice (C-1264), not a
      blemish on a deliverable.

    It fires rarely, and the reason is worth writing down rather than
    discovering twice. Every clean start is already a candidate start, and the
    tie-break above takes the *latest* window of equal score - so a clean start
    that keeps the evidence has usually been chosen before this is reached.
    What is left is the case the ``_MAX_CANDIDATES`` budget hid: a chunk whose
    boundaries ran out before the clean start, which selection therefore never
    saw. Over the four reports measured for C-1534 it moved nothing; the number
    moved because the mark became honest. It is kept because the case is real
    and driven by a test, not because it is the mechanism.
    """

    if opens_cleanly(content, start):
        return start
    wanted = terms & set(tokenize(content[start : start + MAX_CITATION_EXCERPT_CHARS]))
    for index in range(start + 1, min(len(content), start + MAX_CITATION_EXCERPT_CHARS)):
        if not opens_cleanly(content, index):
            continue
        window = content[index : index + MAX_CITATION_EXCERPT_CHARS]
        if len(window) < _MIN_ADVANCED:
            break
        if wanted <= set(tokenize(window)):
            return index
    return start


def citation_excerpt(
    content: str, output_guard: OutputGuard, query: str = "", *, clean_head: bool = False
) -> tuple[str, bool]:
    """Return ``(excerpt, withheld)`` for one cited chunk.

    ``withheld`` is true when evidence exists but the output guard refused to
    show it. That is not the same fact as an empty excerpt and the caller has
    to be able to tell them apart: "we are not showing you this" and "there is
    nothing here" read identically once both are the empty string.

    The cap is applied twice - before and after screening - because the guard
    may redact in place and a redaction can be longer than what it replaced.
    """

    start, excerpt = select_excerpt_span(content, query, clean_head=clean_head)
    if not excerpt:
        return "", False
    # C-1264: a window that drops the head or tail of the chunk ends (or starts)
    # abruptly - mid-word for CJK - and read as broken data with no sign it was
    # clipped. Mark each clipped edge with 「…」, detected on the pre-guard window
    # so a redaction cannot confuse the comparison. The cap still holds: the
    # marks' width is taken out of the body, not added on top.
    head_cut = not content.startswith(excerpt)
    # ...but in ``clean_head`` mode the mark is reserved for a head that is
    # actually broken (C-1534). 「…」 on a window that opens at a heading, a
    # table row or a sentence is true about the chunk and false about the
    # sentence, and on a report bullet the reader only reads the sentence.
    if clean_head and head_cut and opens_cleanly(content, start):
        head_cut = False
    tail_cut = not content.endswith(excerpt)
    guarded = output_guard.scan(excerpt)
    if guarded.blocked:
        return "", True
    lead = "…" if head_cut else ""
    trail = "…" if tail_cut else ""
    budget = MAX_CITATION_EXCERPT_CHARS - len(lead) - len(trail)
    body = guarded.content[:budget]
    # Don't end inside a [REDACTED:...] placeholder. The cut can land mid-marker
    # and leave a meaningless 「[REDACT」 fragment - harmless (the secret is
    # already gone) but, since the excerpt is shown to readers (C-1689/1691), it
    # reads as broken document text. If the budget opened a placeholder it did
    # not close, drop back to its start; the 「…」 already says it was clipped.
    if len(guarded.content) > budget:
        open_bracket = body.rfind("[")
        if open_bracket != -1 and "]" not in body[open_bracket:]:
            tail_frag = body[open_bracket:]
            if "[REDACTED".startswith(tail_frag) or tail_frag.startswith("[REDACTED"):
                body = body[:open_bracket].rstrip()
    # C-1849: don't end inside a number either. When the budget splits a figure -
    # the next dropped character is a digit, so the number continues past the cut -
    # 「1,234,567,890」 shows as 「1,2…」, and a partial number reads as a small whole
    # value, the fidelity a cited figure exists to give (the report body already
    # refuses this, C-1217). Drop the partial back to its start; the 「…」 still says
    # it was clipped. A figure that merely *ends* at the budget (the next character
    # is not another digit) is whole and kept, so no real figure is lost.
    if len(guarded.content) > budget and guarded.content[len(body)] in _DIGITS:
        trimmed = body.rstrip(_NUMBER_TAIL)
        if trimmed:
            body = trimmed
    return lead + body + trail, False
