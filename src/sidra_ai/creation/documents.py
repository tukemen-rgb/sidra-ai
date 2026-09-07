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
from pathlib import Path

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


def _title_from(request: str) -> str:
    stripped = re.split(r"を?(?:作って|作成して|書いて|生成して|つくって|まとめて)", request)[0]
    stripped = re.sub(r"[をのはがにで]+$", "", stripped.strip()).strip()
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
) -> GeneratedDocument:
    """Build one Markdown report from exactly the facts handed in.

    An empty ``facts`` list is a supported input and produces an honest
    skeleton: headings, blanks, and a sources section that says nothing was
    retrieved - which is a document the owner can fill, not a failure.

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
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    retrieved = [fact for fact in (facts or []) if fact.text.strip()]
    sources = list(dict.fromkeys(fact.source for fact in retrieved if fact.source))

    lines: list[str] = [f"# {title}", "", f"> SIDRA AI が {stamp} に生成。数字はすべて下の出典から。", ""]
    unfilled: list[str] = []

    # The module's rule - a number appears only if it was retrieved - held for
    # the body but not the cover. `_title_from` copies the request's subject
    # onto the heading, so a request naming a figure (「解約率30%の改善レポート」
    # 「2024年度の売上」) put that number in the title beside the preamble's
    # promise 「数字はすべて下の出典から」, and `validate_document` could not see
    # it: its number check starts below the first heading. A headline statistic
    # nothing in the evidence supports then read as a sourced, verified figure.
    # Disclosed where the reader looks for gaps - without reprinting the digit,
    # because a number the evidence does not carry is exactly what the validator
    # catches, and the honest disclosure is *that* a figure went unconfirmed,
    # not to smuggle it into the body (the set-aside line's C-1281 choice).
    evidence_text = " ".join(f"{fact.text} {fact.source}" for fact in retrieved)
    title_has_unsourced_number = any(
        token and token not in evidence_text
        for token in (number.strip() for number in NUMBER.findall(title))
    )

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
            f"この文書は「{title}」について、索引した資料から見つかった根拠を"
            "出典つきで下に整理したものです。"
            "確定していない点は〔社長が埋める欄〕として残しています。",
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
            label = fact.source or "出典不明"
            if text not in sources_by_text:
                sources_by_text[text] = []
                order.append(text)
            if label not in sources_by_text[text]:
                sources_by_text[text].append(label)
        for text in order:
            labels = " / ".join(sources_by_text[text])
            lines.append(f"- {text}（出典: {labels}）")
    else:
        lines.append(f"- {BLANK}")
        unfilled.append("わかっていること")
    lines.append("")

    # Present even when everything above is filled: a report that cannot say
    # what it does not know reads as if it knows everything.
    lines += ["## まだ埋まっていないこと", "", f"- {BLANK}"]
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
        lines += [f"- {source}" for source in sources]
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
    path = directory / f"doc-report-{stamp}.md"
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
