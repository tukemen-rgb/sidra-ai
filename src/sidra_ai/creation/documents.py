"""Reports and written documents, under the deck's grounding rule.

「レポートを作って」 has been recognised and unroutable since the DOCUMENT
kind was added to the detector: SIDRA understood and answered "対応する生成器
がまだ登録されていません". This module is that generator, and it inherits the
one rule that makes generated prose safe to hand to an owner:

    **A number appears in the document only if it was retrieved. Otherwise
    the line shows 〔社長が埋める欄〕 and the validator counts it.**

The artifact is Markdown rather than HTML - a document is for editing and
pasting, and Markdown opens in anything, needs no script, and cannot carry
active content into the origin the operator's token lives in. Office
formats stay where they already are: the C-1000 pipeline writes docx/xlsx
around decks, and a second docx writer here would be the same file from two
places.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from sidra_ai.creation.artifact_paths import unique_path
from sidra_ai.creation.vocabulary import (
    drop_english_frame,
    drop_request_adverbs,
    drop_size_phrases,
)
from sidra_ai.creation.evidence import NUMBER, Fact, plain_text

#: Same constant as the deck's, same reason: the renderer and the validator
#: must agree byte-for-byte on what an unfilled slot looks like.
BLANK = "〔社長が埋める欄〕"

#: The sections every report carries, in reading order. Fixed rather than
#: derived from the request: a document whose skeleton depends on phrasing is
#: a document nobody can find their way around twice.
SECTIONS: tuple[str, ...] = ("概要", "わかっていること", "まだ埋まっていないこと", "出典")

#: The sections evidence can actually fill. 「まだ埋まっていないこと」 is blank
#: in every report there has ever been and 「出典」 is not a slot the owner
#: writes into, so a count taken over all of SECTIONS says nothing about
#: whether the report has content in it - it says 3-of-4 for an empty one
#: and would keep C-1128's notice from ever firing.
CONTENT_SECTIONS: tuple[str, ...] = ("概要", "わかっていること")


@dataclass(frozen=True)
class GeneratedDocument:
    title: str
    markdown: str
    #: Section titles that still contain a blank for the owner.
    unfilled: tuple[str, ...] = ()
    evidence: tuple[str, ...] = field(default_factory=tuple)


#: Document-kind nouns a title should not end with, since the artifact already
#: is one: 「競合分析のレポート」→「競合分析」 (C-1246). One alternation with an
#: optional leading 「の」. C-1467: the eight deliverable words C-1458 added to the
#: intent vocabulary so they route to DOCUMENT and generate - 報告書/議事録/
#: マニュアル/提案書/仕様書/要件定義書/手順書/説明書 - were never listed here, so
#: 「会議の議事録」 kept 議事録 on its own heading. Longest first (要件定義書 before
#: the bare 書 forms), matching the tail-anchored strip.
_TITLE_KIND_SUFFIX = re.compile(
    r"の?(?:要件定義書|レポート|ドキュメント|ペーパー|報告書|議事録|マニュアル|提案書"
    r"|仕様書|手順書|説明書|文書|資料|まとめ|report|document|doc)$",
    re.IGNORECASE,
)

#: The 「about X」 phrase a request uses to point at its subject: 「Xについての
#: レポート」. Dropping the kind word leaves 「Xについて」, and the 概要 template
#: 「この文書は「{title}」について」 then says について twice (C-1255). Anchored to
#: the tail so a subject that merely contains 「について」 mid-phrase is untouched.
_TITLE_ABOUT_SUFFIX = re.compile(r"(?:について(?:の)?|に関して(?:の)?|に関する)$")

#: The file format a request names to say how to render the document
#: (「売上のレポートをWordで作って」「競合分析をPDFでまとめて」). C-1484, the document
#: twin of the deck C-1465. The tail-anchored kind strip cannot reach a kind word
#: pushed off the tail by a trailing 「…をWordで」, and the format word is not a
#: kind word, so it rode into the title (「売上のレポートをWord」). Gated to a
#: preceding を/の - which is where the instrumental phrase puts the format word,
#: and which キーワード/パスワード never satisfy (their ワード follows ス/ー), so a
#: subject that merely ends in ワード survives; a bare leading 「Wordで報告書」
#: (no subject to corrupt) fails the lookbehind and is left alone rather than
#: peeled to nothing.
_DOC_FORMAT_SUFFIX = re.compile(
    r"(?<=[をの])(?:ワード|エクセル|word|excel|pdf|docx|xlsx)$",
    re.IGNORECASE,
)

#: The requested-format word mapped to the name shown to the operator. C-1834:
#: the document generator only ever writes Markdown, so a request that names a
#: format it cannot produce is told so - the document twin of the deck's pptx
#: notice (C-1465). Keyed lowercase; カナ keys are unchanged by ``lower()``.
_FORMAT_LABEL: dict[str, str] = {
    "word": "Word", "ワード": "Word", "docx": "Word（.docx）",
    "excel": "Excel", "エクセル": "Excel", "xlsx": "Excel（.xlsx）",
    "pdf": "PDF",
}


def requested_format(request: str) -> str:
    """The file format a request asked the report to be rendered in, when it is
    one the document generator does not produce (it only writes Markdown).

    Uses the same gate C-1484 uses to strip the word from the title: after the
    making verb is cut and the trailing particle dropped, a format word sitting
    right after を/の is the instrumental 「…をWordで」. Returns the operator-facing
    name (「Word」/「PDF」…) or "" when no such format was named - so 「Wordの使い方」
    (word as the subject) and 「PDFで管理する方法」 return "".
    """

    head = re.split(r"を?(?:作って|作成して|書いて|生成して|つくって|まとめて)", request)[0]
    head = re.sub(r"[をのはがにで]+$", "", head.strip()).strip()
    match = _DOC_FORMAT_SUFFIX.search(head)
    return _FORMAT_LABEL.get(match.group(0).lower(), "") if match else ""

#: A length the request asks the report to run to, sitting in front of the
#: subject: 「3ページのレポート」「2000字のレポート」「5枚の売上のレポート」. C-1822:
#: this is a length, not a subject, but the tail-anchored kind/format/about peels
#: never reach a leading phrase, so 「3ページ」 rode onto the cover as the title -
#: and, being a number with no evidence behind it, then failed the body
#: number-check 「numbers not present in the evidence: 3」. Stripped once, before
#: the peel loop, so 「3ページのレポート」 falls to the default title and
#: 「3ページの競合分析のレポート」 titles 「競合分析」. Gated to a real length unit
#: (ページ/頁/字/文字/枚) closed by の or the end, so a number that is part of a
#: real subject survives: 第3四半期 (四半期 is not a unit), 3年計画 (年), G3 (no
#: leading digit), 5枚組の写真集 (枚 is followed by 組, not の/end), 300万円の予算 (万).
_DOC_LENGTH_PREFIX = re.compile(r"^[0-9０-９]+(?:ページ|頁|字|文字|枚)(?:の|$)")

#: The same length, sitting *behind* the subject instead of in front of it:
#: 「レポートを3ページで作って」「ドキュメントを3ページ」「売上のレポートを2000字で」.
#: C-1842: C-1822 stripped a leading length, but the tail-anchored kind/format/
#: about peels never reach a length in this position, so 「3ページ」 rode onto the
#: cover as the title - and, being a number with no evidence behind it, then failed
#: the body number-check 「numbers not present in the evidence: 3」 (the title's
#: subject is copied into the 概要 and the subject-unmatched disclosure line). This
#: is the exact failure C-1822 was created to prevent, on the more natural
#: phrasing. Stripped once, right after the leading strip, so both ends fall away
#: before the peel loop and the empty-title guard keeps a bare kind word. Gated to
#: a preceding を/の (where the instrumental length phrase attaches) and a real
#: length unit closed by the tail, so a subject number survives: 第3四半期 (四半期
#: is not a unit), 5枚組の写真集 (枚 is not at the tail), 3年計画 (年), and a genuine
#: headline statistic 「解約率30%」 (% is not a length unit) stays to fail validation.
_DOC_LENGTH_SUFFIX = re.compile(r"(?:を|の)[0-9０-９]+(?:ページ|頁|字|文字|枚)$")


def _title_from(request: str) -> str:
    stripped = re.split(r"を?(?:作って|作成して|書いて|生成して|つくって|まとめて)", request)[0]
    # C-1829: the words about when to write it, not what to write.
    # C-1841: 「write a report about monetisation」 was the whole sentence.
    stripped = drop_english_frame(stripped)
    # And the size, which _DOC_LENGTH_PREFIX below only catches at the start
    # and only in Japanese: 「write a 3 page report」 was titled 「3 page」, and
    # 「収益化のレポートを3ページで作って」 - the size behind the kind word rather
    # than in front of it - was titled 「収益化のレポートを3ページ」, keeping the
    # kind word too because the strip that removes it is anchored to the end.
    # Both are the shape C-1833 fixed for the deck.
    stripped = drop_size_phrases(stripped)
    stripped = drop_request_adverbs(stripped)
    stripped = re.sub(r"[をのはがにで]+$", "", stripped.strip()).strip()
    stripped = _DOC_LENGTH_PREFIX.sub("", stripped).strip()
    # ...and the same length when it trails the subject (C-1842).
    stripped = _DOC_LENGTH_SUFFIX.sub("", stripped).strip()
    # The subject alone: a report titled 「競合分析のレポート」 says 「レポート」
    # in its heading, its 概要 and its confirmation, all beside a file that is a
    # report (C-1246). Then the 「について/に関する」 the request pointed with, so
    # 「広告方針についてのレポート」 does not title 「広告方針について」 and double
    # the について in the 概要 (C-1255). C-1467: peel the trailing particle, kind
    # word and about-phrase repeatedly - a request stacks two kind words behind a
    # particle (「レポートをドキュメントで」) or an about phrase behind a kind word
    # (「に関する報告書」), and stripping each once dropped only the outer one,
    # leaving the inner kind word on the cover. Each pass only shrinks, so the
    # equality check terminates it; a single kind word settles in one pass, and a
    # request that is only a kind word ("レポートを作って") keeps it rather than
    # emptying out.
    peeled = stripped
    while True:
        step = re.sub(r"[をのはがにで]+$", "", peeled).strip()
        step = _DOC_FORMAT_SUFFIX.sub("", step).strip()
        step = _TITLE_KIND_SUFFIX.sub("", step).strip()
        step = _TITLE_ABOUT_SUFFIX.sub("", step).strip()
        if step == peeled:
            break
        peeled = step
    if peeled:
        stripped = peeled
    return stripped[:60] or "レポート"


def generate_document(
    request: str,
    *,
    facts: list[Fact] | None = None,
    now: datetime | None = None,
    set_aside: int = 0,
    subject_unmatched: bool = False,
) -> GeneratedDocument:
    """Build one Markdown report from exactly the facts handed in.

    An empty ``facts`` list is a supported input and produces an honest
    skeleton: headings, blanks, and a sources section that says nothing was
    retrieved - which is a document the owner can fill, not a failure.

    ``subject_unmatched`` says the filter could see the subject and not one
    retrieved fact carried it. The facts are still printed - setting them
    all aside produced blank headings (C-1403) - but the reader is told,
    because 「根拠 5 件」 over five facts about other subjects is the
    overclaim this report was making (C-1532).

    ``set_aside`` is how many retrieved facts the caller dropped as off-topic
    before handing over ``facts`` (C-1281). The summary says so, but the summary
    is shown once and the file is the artifact that is saved, edited and
    forwarded - a report that quietly leaves out evidence reads as the complete
    sourced picture it is not. So when any were set aside the file discloses it
    too, in 「まだ埋まっていないこと」. No count is printed: a digit that names
    nothing in the evidence is exactly what ``validate_document`` catches as a
    fabricated number, and the honest thing to disclose here is *that* evidence
    was withheld, not to smuggle a figure past the check.
    """

    title = _title_from(request)
    # C-1483: the deck/art/game/3D preview all run fact and request text through
    # `escape()` before it enters their HTML; the report (.md) did not, so a
    # `<script>` on a fact or in the request title - allowed into the index by
    # the gate, which screens for secrets and injection, not HTML - was written
    # raw and ran when the file was opened in a Markdown renderer that permits
    # inline HTML. Escape at markdown-construction: the tag then shows as the
    # literal text the source held. `title` stays raw for `.title` and the number
    # check; `safe_title` is the escaped form the document displays. quote=False
    # keeps apostrophes/quotes literal for a file meant to be read and edited -
    # neutralising `<`, `>` and `&` is what stops a tag from forming.
    safe_title = escape(title, quote=False)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    retrieved = [fact for fact in (facts or []) if fact.text.strip()]
    sources = list(dict.fromkeys(fact.labelled_source for fact in retrieved if fact.source))

    # The module's rule - a number appears only if it was retrieved - held for
    # the body but not the cover. `_title_from` copies the request's subject
    # onto the heading, so a request naming a figure (「解約率30%の改善レポート」
    # 「2024年度の売上」) put that number in the title, and `validate_document`
    # could not see it: its number check starts below the first heading. A
    # headline statistic nothing in the evidence supports then read as a
    # sourced, verified figure. It is disclosed where the reader looks for gaps,
    # in 「まだ埋まっていないこと」 below, without reprinting the digit (C-1476).
    evidence_text = " ".join(f"{fact.text} {fact.source}" for fact in retrieved)
    title_has_unsourced_number = any(
        token and token not in evidence_text
        for token in (number.strip() for number in NUMBER.findall(title))
    )

    # The preamble made the same promise the body validator enforces -
    # 「数字はすべて下の出典から」 - unconditionally, one line under the very
    # figure the evidence does not support. That blanket claim, next to an
    # unsourced headline number, read as if SIDRA had verified it - the exact
    # impression this module exists to prevent, landing on the cover, while the
    # document itself discloses two sections down that the figure is unconfirmed.
    # So the cover states the truth the module already computed: when the title
    # carries an unsourced number, scope the promise to the body and name the
    # gap where the reader first meets the figure, instead of asserting every
    # number is sourced. A clean title keeps the original assurance (C-1772).
    if title_has_unsourced_number:
        preamble = (
            f"> SIDRA AI が {stamp} に生成。本文の数字は下の出典から。"
            "タイトルの数値は索引した根拠では確認できていません"
            "（「まだ埋まっていないこと」参照）。"
        )
    elif not retrieved:
        # C-1803. C-1772 scoped the promise when the title carried an unsourced
        # number, but a number-free title with no evidence at all fell through to
        # the blanket claim below. The body is then entirely 〔社長が埋める欄〕,
        # 「出典」 names none, and 「まだ埋まっていないこと」 states the miss - yet the
        # cover promised 「数字はすべて下の出典から」, a sourcing discipline for a
        # document with zero sources and zero numbers. Reopened or forwarded on
        # its own the cover read as a normal sourced report while the chat reply
        # admitted 「中身のある資料を作れませんでした」. State the truth the module has
        # already computed, and make no sourcing promise. (An empty draft whose
        # title carries a number still uses the branch above, keeping C-1772.)
        preamble = (
            f"> SIDRA AI が {stamp} に生成。"
            "索引にこの依頼の根拠が無く、本文はまだ空の下書きです（数字は入っていません）。"
        )
    else:
        preamble = f"> SIDRA AI が {stamp} に生成。数字はすべて下の出典から。"

    lines: list[str] = [f"# {safe_title}", "", preamble, ""]
    unfilled: list[str] = []

    lines += ["## 概要", ""]
    if retrieved:
        # Not the first retrieved fact copied whole: that fact also opens
        # 「わかっていること」 below, so copying it here printed the same
        # paragraph twice, and a 「概要」 that is only the top BM25 hit is not
        # a summary of anything - naming it one is the overclaim this project
        # refuses elsewhere (C-1232). With no model to summarize, 概要 states
        # what the document *is* instead. No digit reaches the line, so the
        # fabrication validator has nothing to catch.
        lines += [
            (
                f"この文書は「{safe_title}」について、索引した資料から見つかった根拠を"
                "出典つきで下に整理したものです。"
                "確定していない点は〔社長が埋める欄〕として残しています。"
                if not subject_unmatched
                # C-1532: the 概要 is where a reader decides how much to
                # trust the rest, so the caveat goes here rather than only
                # in a section further down that a skim never reaches.
                else f"**索引した資料の中に「{safe_title}」に触れているものは"
                "ありませんでした。**下に並べているのは検索が返した資料"
                "そのままで、主題と重なる語は含まれていません。"
                "主題についての根拠として読まないでください。"
            ),
            "",
        ]
    else:
        lines += [BLANK, ""]
        unfilled.append("概要")

    lines += ["## わかっていること", ""]
    if retrieved:
        # Two files often carry the identical passage (a policy line copied
        # into another doc), so retrieval hands back facts with the same text
        # and the report printed a bullet for each - the reader reads the same
        # sentence twice (C-1242). Identical text is merged into one bullet
        # whose 「出典」 names every file, so the passage is stated once while
        # "both files say this" survives (the answer's C-1241 choice, here).
        sources_by_text: dict[str, list[str]] = {}
        order: list[str] = []
        for fact in retrieved:
            # C-1288: the answer path (echo `_lead`) and the deck already run
            # retrieved evidence through `plain_text`; the report did not, so a
            # fact carrying Markdown printed 「## 概況」 raw inside a bullet and a
            # table collapsed to one unreadable run of 「| --- |」 bars when the
            # whitespace join ate its newlines. Same flatten here: decoration
            # becomes prose, a table reads as 「セル / セル；」, every word and
            # number survives, so the fabrication check still sees the figures.
            text = plain_text(fact.text)
            label = fact.labelled_source or "出典不明"
            if text not in sources_by_text:
                sources_by_text[text] = []
                order.append(text)
            if label not in sources_by_text[text]:
                sources_by_text[text].append(label)
        for text in order:
            labels = " / ".join(sources_by_text[text])
            lines.append(f"- {escape(text, quote=False)}（出典: {escape(labels, quote=False)}）")
    else:
        lines.append(f"- {BLANK}")
        unfilled.append("わかっていること")
    lines.append("")

    # Present even when everything above is filled: a report that cannot say
    # what it does not know reads as if it knows everything.
    lines += ["## まだ埋まっていないこと", "", f"- {BLANK}"]
    if subject_unmatched:
        lines.append(
            f"- 「{safe_title}」そのものについての根拠は、索引の中に見つかりませんでした"
            "（上の資料は主題と重なる語を持ちません）。"
        )
    if set_aside > 0:
        lines.append(
            "- 依頼と主題が重ならないと判断した根拠は、この文書には載せていません"
            "（依頼を具体的にすると入ります）。"
        )
    if title_has_unsourced_number:
        lines.append(
            "- タイトルに含まれる数値は、索引した根拠では確認できませんでした"
            "（社長がご確認ください）。"
        )
    lines.append("")
    unfilled.append("まだ埋まっていないこと")

    lines += ["## 出典", ""]
    if sources:
        lines += [f"- {escape(source, quote=False)}" for source in sources]
    else:
        lines.append("- （この依頼で索引から根拠は見つかりませんでした）")
    lines.append("")

    return GeneratedDocument(
        title=title,
        markdown="\n".join(lines),
        unfilled=tuple(unfilled),
        evidence=tuple(sources),
    )


def save_document(document: GeneratedDocument, data_dir: str | Path) -> Path:
    directory = Path(data_dir) / "artifacts"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = unique_path(directory, f"doc-report-{stamp}", ".md")
    path.write_text(document.markdown, encoding="utf-8")
    return path


def validate_document(
    document: GeneratedDocument, facts: list[Fact] | None = None
) -> dict:
    """Every reason the document is not trustworthy, not just the first.

    The load-bearing check mirrors the deck's: a figure in the body that
    appears in no retrieved fact was made up, however plausible the sentence
    around it reads. The generation date in the preamble is exempt by
    construction - the check starts below the first heading's blank line.
    """

    failures: list[str] = []
    if not document.markdown.startswith("# "):
        failures.append("no title heading")
    for section in SECTIONS:
        if f"## {section}" not in document.markdown:
            failures.append(f"missing section: {section}")

    # Source labels join the allowed text: a path like ``PR-17.md`` puts a
    # digit on the page, and that digit came from the corpus as surely as
    # the fact it labels.
    evidence = " ".join(f"{fact.text} {fact.source}" for fact in (facts or []))
    body = document.markdown.split("## ", 1)[-1]
    unsourced: list[str] = []
    for line in body.splitlines():
        if BLANK in line or line.startswith("## "):
            continue
        for number in NUMBER.findall(line):
            token = number.strip()
            if token and token not in evidence:
                unsourced.append(token)
    if unsourced:
        failures.append(
            "numbers not present in the evidence: " + ", ".join(unsourced[:5])
        )

    return {
        "usable": not failures,
        "failures": failures,
        "unfilled": list(document.unfilled),
        "sources": len(document.evidence),
    }


__all__ = [
    "BLANK",
    "CONTENT_SECTIONS",
    "GeneratedDocument",
    "SECTIONS",
    "generate_document",
    "save_document",
    "validate_document",
]
