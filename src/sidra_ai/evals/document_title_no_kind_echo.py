"""Does a report's title echo the word 「レポート」 the request already said?

C-1246: ``_title_from`` kept the whole request phrase before the make-verb, so
「競合分析のレポートを作って」 titled the report 「競合分析のレポート」. The
document is a report, so the kind word then appeared twice: the heading
「# 競合分析のレポート」, the 概要 「この文書は『競合分析のレポート』について」,
and the confirmation 「『競合分析のレポート』のレポートを作りました」. The title
should be the subject alone (「競合分析」), so each of the three reads once.

The checks build real documents from requests that do and do not end in a
document-kind word, and confirm the trailing kind word is dropped from the
title (and so from the 概要 and the confirmation), that a request with no kind
word is untouched, and that a bare 「レポートを作って」 still falls back to a
non-empty title.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Document-kind nouns a report title should not end with - the file already is
#: one. Mirrors the strip list in ``documents._title_from``.
_KINDS = ("レポート", "文書", "ドキュメント", "資料", "まとめ", "ペーパー")


@dataclass(frozen=True)
class DocumentTitleNoKindEchoResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _confirmation(title: str) -> str:
    # The shape document_job.py builds; reproduced so the check does not have to
    # write a file. Only the title varies, which is what this eval is about.
    return f"「{title}」のレポートを作りました"


def evaluate_document_title_no_kind_echo() -> DocumentTitleNoKindEchoResult:
    from sidra_ai.creation.documents import generate_document
    from sidra_ai.creation.evidence import Fact

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # 1: a 「…のレポート」 request titles the report by its subject only. A fact
    # is supplied so the 概要 line (which only renders with content) exists to
    # be checked at all.
    facts = [Fact("競合は 3 社に絞れる。", "tukemen-rgb/site docs/competitive-analysis.md")]
    doc = generate_document("競合分析のレポートを作って", facts=facts)
    add(doc.title == "競合分析", f"title kept the kind word: 「{doc.title}」")

    # 2: the 概要 line names the subject once, not the doubled phrase.
    add(
        "「競合分析」について" in doc.markdown
        and "競合分析のレポート」" not in doc.markdown,
        "概要 still doubles the kind word",
    )

    # 3: the confirmation reads once, not 「…レポート」のレポート.
    conf = _confirmation(doc.title)
    add(
        "「競合分析」のレポートを作りました" == conf,
        f"confirmation doubles the kind word: {conf}",
    )

    # 4: another kind word (資料) is stripped too.
    doc2 = generate_document("売上の資料を作って")
    add(doc2.title == "売上", f"資料 not stripped: 「{doc2.title}」")

    # 5: a request with no kind word is left exactly as it was.
    doc3 = generate_document("競合分析を作って")
    add(doc3.title == "競合分析", f"non-kind title changed: 「{doc3.title}」")

    # 6: a bare kind word still yields a non-empty title, not "".
    doc4 = generate_document("レポートを作って")
    add(bool(doc4.title.strip()), "bare kind word produced an empty title")

    # 7: the title never ends in a kind word for a kind-word request - a
    # general guard across the list, not only the two cases above.
    bad = [
        k
        for k in _KINDS
        if generate_document(f"月次{k}を作って").title.endswith(k)
    ]
    add(not bad, f"these kinds survived at the title end: {bad}")

    # 8: a kind word that is part of the subject, not its tail, is kept - the
    # strip is anchored to the end, not a match-anywhere that would maul
    # 「資料室の分析」 into 「室の分析」.
    doc5 = generate_document("資料室の分析を作って")
    add(doc5.title == "資料室の分析", f"a mid-phrase kind word was stripped: 「{doc5.title}」")

    return DocumentTitleNoKindEchoResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=8,
        failures=tuple(failures),
    )


__all__ = ["DocumentTitleNoKindEchoResult", "evaluate_document_title_no_kind_echo"]
