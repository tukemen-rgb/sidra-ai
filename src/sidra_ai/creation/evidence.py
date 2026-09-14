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
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from sidra_ai.retrieval.search import subject_evidence_probes, tokenize

#: Anything that looks like a quantity. Deliberately broad - a false positive
#: costs one extra evidence check, a false negative puts an unsourced number
#: in front of a reader, which is the failure this whole path exists to
#: prevent.
NUMBER = re.compile(r"\d[\d,.\s]*\s*(?:%|％|円|万|億|人|件|倍|pt|x)?", re.IGNORECASE)


#: A digit that only names a thing, not a quantity: it follows an ASCII letter,
#: across at most one hyphen. BM25, FTS5, GPT-6, backlog ids like C-1234, S3 and
#: v0.1 are names; 14/38, 512 MiB, 60Hz, 3件 and the 20万円 in 「GPT4は月20万円」
#: stay figures - only GPT4 is masked, and the continuation class is ASCII-only
#: on purpose, because a \w continuation matches CJK and would let the mask
#: swallow the Japanese figure that follows an identifier (C-1609).
_IDENTIFIER = re.compile(r"[A-Za-z]+-?\d[\dA-Za-z.]*")

#: C-1815. A bare year is a date, not a supporting figure - the sibling of the
#: identifier digit above. The 根拠となる数字 slide is chosen by whether a fact
#: carries a figure, but a fact whose only number is a start-year
#: (「収益化は2024年に開始した」「創業は1998年」) is not evidence in the pitch sense; it
#: was landing on the "backing numbers" slide and reading as a metric. Masked
#: before the figure test so such a fact no longer counts. The 年 suffix is
#: required, so a four-digit amount with a unit (「2024万円」) is left a figure, and
#: a real metric beside a year (「2024年に3倍」) still counts because 「3倍」 survives.
_YEAR = re.compile(r"(?:19|20)\d{2}年")


#: Markdown decoration inside an excerpt window. The corpus is Markdown, so
#: a 200-character window lands mid-document and drags ``##``, ``**`` and
#: ``>`` into slide bullets as literal characters (C-1212). Only decoration
#: is removed - the words are the evidence and must survive unchanged.
_MD_HEADING = re.compile(r"(?:(?<=\s)|^)#{1,6}\s+")
_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")
#: A ``**`` left over after the pairs are gone (C-1443). Chunking cuts a
#: document every ~1200 characters without regard for markup, so a bold
#: span that straddles the cut arrives here as half a span: measured on
#: this repo's own docs, 95 of the 940 chunks that carry ``**`` hold an
#: odd number of them, and every one of those used to show the reader a
#: raw ``**``.
#:
#: What may NOT be dropped is a ``**`` that is content rather than
#: decoration, because losing a real character out of quoted evidence is
#: worse than showing a marker. Two such shapes are in the corpus and
#: both are kept: one standing alone between spaces (13 of them - the
#: line 「③閉じない ** の残存」 says it about this very bug), and one
#: ending a path (3 of them, 「src/sidra_ai/security/**」). What is left
#: is a marker hugging the text it was decorating, which is the only
#: shape emphasis can take.
_MD_BOLD_DANGLING = re.compile(r"\*\*")


def _drop_dangling_bold(text: str) -> str:
    """Remove a ``**`` that is decoration; keep one that is content.

    Decoration hugs the words it decorates, so a leftover marker with
    text against it on either side is half a bold span. Two shapes are
    content and are kept: one standing between spaces, and one belonging
    to a path - ``docs/**``, ``a/**/b``, ``src/sidra_ai/security/**``.
    The path test looks at BOTH sides, which a first version did not:
    it kept ``security/**`` and quietly ate the stars out of
    ``docs/**<br>`` and ``a/**/b``, because those have text after them.
    """

    out: list[str] = []
    last = 0
    for spot in _MD_BOLD_DANGLING.finditer(text):
        before = text[spot.start() - 1 : spot.start()] if spot.start() else ""
        after = text[spot.end() : spot.end() + 1]
        touching = (before and not before.isspace()) or (after and not after.isspace())
        in_a_path = before == "/" or after == "/"
        if touching and not in_a_path:
            out.append(text[last : spot.start()])
            last = spot.end()
    out.append(text[last:])
    return "".join(out)
_MD_EMPHASIS = re.compile(r"(?<![\w*])\*([^*\s][^*]*)\*(?![\w*])")
_MD_CODE = re.compile(r"`([^`]+)`")
#: A fenced code block's delimiter line - three or more backticks or tildes (up
#: to three leading spaces, per CommonMark), plus any info string. Removed whole
#: so the fence marks never reach the reader: ``_MD_CODE`` only strips an inline
#: single-backtick span, so a triple fence otherwise lost one backtick per side
#: and left a 「``」 artifact, and a ``~~~`` fence survived untouched. The code
#: text between the fences is kept - it is content, like any other line.
_MD_FENCE = re.compile(r"(?m)^[ \t]*(?:`{3,}|~{3,})[^\n]*$")
#: A setext H1 heading's underline - a line of only ``=`` (CommonMark allows any
#: number, plus leading/trailing space). Pure syntax, no content, removed whole so
#: 「タイトル\n===」 does not flatten to 「タイトル ===」 with a raw ``===`` artifact
#: (C-1709). ATX ``#`` headings go through ``_MD_HEADING``, and a setext H2's
#: ``---`` underline is already caught by ``_MD_TABLE_SEP`` (a ``-{2,}`` line), but
#: a ``=`` line had no case. Line-anchored, so a mid-line ``=`` (「key=value」, an
#: equation) is never touched - only a line that is nothing but ``=``.
_SETEXT_UNDERLINE = re.compile(r"(?m)^[ \t]*=+[ \t]*$")
_MD_QUOTE = re.compile(r"(?:(?<=\s)|^)>\s?")
#: A Markdown link. The corpus cross-references its own files, so an excerpt
#: carries 「[SPEC.md](../SPEC.md)」 - and when the URL trips the output guard's
#: entropy check it becomes 「[SPEC.md](../[REDACTED:high_entropy:…].md)」, an
#: alarming placeholder in what is just a relative path (C-1227). Keep the link
#: text (the words the reader needs); drop the brackets and the URL. The second
#: pattern catches a link the excerpt window cut mid-URL (「[docs/x.md](..」).
#: A bare 「[1]」 reference has no following 「(」 and is left alone.
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MD_LINK_OPEN = re.compile(r"\[([^\]]+)\]\([^)\n]*")
#: A list marker at the start of a line: a bullet (with or without a task
#: checkbox) or an ordered-list number (「2.」「3)」). Only line-anchored, so a
#: mid-sentence dash (「令和 - 平成」) and an inline decimal (「3.5 倍」, whose
#: dot is followed by a digit, not a space) are never touched. When an excerpt
#: window lands inside an ordered list, the numbers used to survive - a
#: document's 概要 opened 「2. ブランドを分けるか」 with no 1 (C-1222) - because
#: only bullets were stripped. Applied before whitespace collapse, while the
#: line starts still exist (C-1216).
_MD_LIST = re.compile(r"(?m)^[ \t]*(?:[-*+]|\d{1,3}[.)])[ \t]+(?:\[[ xX]\][ \t]+)?")

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

#: A Markdown table's separator row (「| --- | --- |」, 「|:--|--:|」) - pure
#: syntax, no content, so it is removed whole. The README stats, the FAQ
#: verdict tables and the decision tables all carry one, and it used to land in
#: an answer as 「| --- | --- |」 (C-1226). Only pipes, dashes, colons and
#: spaces, with at least one run of dashes, so a real sentence never matches.
_MD_TABLE_SEP = re.compile(r"(?m)^[ \t]*\|?[ \t:|]*-{2,}[ \t:|-]*$")
#: A table body/header row: starts and ends with a pipe. Its cells become a
#: 「 / 」-joined phrase so the row reads as prose instead of a wall of bars.
#: Line-anchored on both ends, so a mid-sentence 「a|b」 is never touched.
_MD_TABLE_ROW = re.compile(r"(?m)^[ \t]*\|(?P<cells>.+)\|[ \t]*$")

#: Ends a flattened row (C-1245). ``plain_text`` finishes with
#: ``" ".join(text.split())``, which collapses the newlines between rows, so a
#: multi-row table would run together and the 「 / 」 inside a row would be
#: indistinguishable from the space between rows. A delimiter that is not
#: whitespace survives the collapse, keeping 「項目 / 内容」 and 「運営歴 / 約20年」
#: visibly two rows. Not a sentence terminator, so :func:`whole_sentences`
#: does not treat a row boundary as the end of the excerpt.
_TABLE_ROW_END = "；"


def _flatten_table_row(match: "re.Match[str]") -> str:
    cells = [cell.strip() for cell in match.group("cells").split("|")]
    joined = " / ".join(cell for cell in cells if cell)
    return joined + _TABLE_ROW_END if joined else joined


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

    A Markdown table is flattened rather than shown as bars (C-1226): its
    separator row is dropped and each body row's cells are joined with 「 / 」,
    so a stats table reads as prose instead of 「| --- | --- |」. Each row also
    ends with 「；」 (C-1245), because the final whitespace collapse would
    otherwise merge the rows into one run where 「 / 」 and the row break look
    the same.

    A Markdown link keeps its text and loses its URL (C-1227): 「[SPEC.md](../
    SPEC.md)」 becomes 「SPEC.md」, so the brackets and a possibly-redacted URL
    do not reach the reader. A bare 「[1]」 with no 「(」 after it is untouched.
    """

    text = _TRAILER.sub("", text)
    # Tables before the list strip, so a separator row is gone before its
    # dashes could read as a bullet, and while line boundaries still exist.
    text = _MD_TABLE_SEP.sub("", text)
    text = _MD_TABLE_ROW.sub(_flatten_table_row, text)
    # Fence delimiter lines go before the list/heading/code strips and while line
    # boundaries still exist, so a triple-backtick fence cannot leave a 「``」
    # artifact and a ~~~ fence cannot survive whole (C-1695).
    text = _MD_FENCE.sub("", text)
    # A setext H1 underline (a line of only ``=``) goes next, alongside the fence
    # and table-separator removals, while line boundaries still exist - otherwise
    # the ``=`` line survives whitespace collapse as a raw 「===」 artifact (C-1709).
    text = _SETEXT_UNDERLINE.sub("", text)
    text = _MD_LIST.sub("", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_BOLD.sub(r"\1", text)
    # ...and then whatever half-span the chunker handed us (C-1443).
    text = _drop_dangling_bold(text)
    text = _MD_EMPHASIS.sub(r"\1", text)
    text = _MD_CODE.sub(r"\1", text)
    text = _MD_QUOTE.sub("", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_LINK_OPEN.sub(r"\1", text)
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


#: Japanese notes for a source whose trust is not the internal-repo norm,
#: mirroring the chat citation labels (C-1471; ask_cli._TRUST_LABELS and the web
#: UI's TRUST_LABELS). internal_repo and an empty/unknown level get no note, so
#: an ordinary in-house fact reads exactly as it did before C-1831.
_TRUST_NOTE: dict[str, str] = {
    "external": "外部",
    "unverified": "未検証",
    "operator": "運用者",
    "system": "システム",
}


@dataclass(frozen=True)
class Fact:
    """One retrieved claim and where it came from.

    ``source`` is a repository-and-path label. ``text`` is passage text the
    caller has already taken from an allowed chunk - a generator never reads
    a document itself. ``trust_level`` is the source's provenance trust (the
    string form of :class:`~sidra_ai.documents.TrustLevel`), so a forwardable
    artifact can flag a third-party or unverified source the way the chat
    citation does (C-1831); empty means unspecified and reads as internal.
    """

    text: str
    source: str
    trust_level: str = ""

    @property
    def labelled_source(self) -> str:
        """``source`` with a trust note when it is not the internal-repo norm.

        The document report and deck HTML are opened and forwarded, so a source
        the chat citation would flag 「外部」/「未検証」 (C-1471) must carry the same
        note here or a third party's unverified claim reads as an internal fact
        (C-1831). An empty source, or an internal/empty/unknown trust level, is
        returned unchanged.
        """

        note = _TRUST_NOTE.get(self.trust_level, "")
        if not self.source or not note:
            return self.source
        return f"{self.source}（{note}）"

    def mentions_number(self) -> bool:
        # Mask an identifier's digits first, so a name that carries a digit
        # (BM25, C-1234) is not read as a supporting figure (C-1609); then mask
        # bare years, a date rather than a metric (C-1815). A real figure beside
        # either survives both masks.
        return bool(NUMBER.search(_YEAR.sub(" ", _IDENTIFIER.sub(" ", self.text))))


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

    latin, windows = _subject_probes(request)
    if not latin and not windows:
        return list(facts), []
    kept, aside = [], []
    for fact in facts:
        (kept if _about(latin, windows, fact) else aside).append(fact)
    if not kept:
        return list(facts), []
    return kept, aside


@lru_cache(maxsize=1)
def _artifact_mask() -> "re.Pattern[str]":
    """The artifact nouns, so they can be cut out of the request first.

    Subtracting an artifact's *probes* afterwards is not enough, and the
    measured reason is 「進捗レポートを作って」: kanji and katakana run
    together with no kana between them, so the run is 進捗レポート and its
    three-character windows are 進捗レ and 捗レポ - straddling the subject
    and the artifact noun, matching neither on its own. A fact that says
    「進捗は 3 件です」 then failed to match its own subject, which is the
    C-1403 case this must never touch. Cutting the noun out before the runs
    are formed leaves 進捗, and the window is the subject again.

    Longest first, so 「3dモデル」 is removed whole rather than leaving a
    stray 「3d」 behind.
    """

    from sidra_ai.creation.intent import _ARTIFACTS

    words = sorted(
        {word for words in _ARTIFACTS.values() for word in words},
        key=len,
        reverse=True,
    )
    return re.compile("|".join(re.escape(word) for word in words), re.IGNORECASE)


def _subject_probes(request: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """What proves a fact shares this request's subject.

    The answer path's probes (C-1510's three-character windows, plus
    C-1512's lone-kanji nouns), taken from the request with the artifact
    noun cut out. The report used :func:`subject_terms` instead, and the
    difference was the C-1532 defect: a one-character subject has no
    two-character term to be found in, so 「犬の飼い方のレポート」 offered the
    filter nothing at all and five facts about other things were printed as
    根拠. The answer path could already see 犬; the report was asking a
    weaker question than its own sibling.
    """

    return subject_evidence_probes(_artifact_mask().sub(" ", request))


def _about(latin: Sequence[str], windows: Sequence[str], fact: Fact) -> bool:
    """Whether one fact carries the subject, matched as the answer path does."""

    if latin and set(latin).intersection(tokenize(fact.text)):
        return True
    if not windows:
        return False
    content = unicodedata.normalize("NFKC", fact.text).casefold()
    return any(window in content for window in windows)


def subject_unmatched(request: str, facts: Sequence[Fact]) -> bool:
    """Whether ``on_topic`` kept everything because *nothing* matched.

    ``on_topic`` stands down in two situations and its return value cannot
    tell them apart: a request whose subject it cannot see at all, and a
    request whose subject it can see and no retrieved fact carries. The
    second is what a reader has to be told, and it is the C-1532 defect:
    the report announced 「根拠 5 件」 over five facts about other subjects,
    each printed under 「わかっていること」 with a repository path beside it,
    while the deck asked per slide and left the slides honestly blank.

    The stand-down itself is right and stays (C-1403): 「進捗レポート」 over
    this repository is built from evidence that does not contain the word
    進捗, and setting all of it aside produced a document of blank headings.
    So this changes no filtering - the facts are kept either way. It is the
    sentence beside them that was wrong.
    """

    latin, windows = _subject_probes(request)
    if not latin and not windows:
        return False
    return not any(_about(latin, windows, fact) for fact in facts)


__all__ = ["Fact", "NUMBER", "on_topic", "subject_unmatched"]
