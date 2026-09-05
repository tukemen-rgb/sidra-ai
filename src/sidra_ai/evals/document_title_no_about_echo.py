"""Does a report's title keep the 「について」 the request used to point at it?

C-1255: C-1246 dropped the document-kind word from the title, but the about
phrase 「について」/「に関する」 stayed. 「広告方針についてのレポートを作って」 then
titled the report 「広告方針について」, and the 概要 template 「この文書は「{title}」
について」 produced 「『広告方針について』について」 - about twice. 「Xについての
レポート」 is an ordinary way to ask, so this is common; the title should be the
subject alone (「広告方針」).

The checks build reports from about-phrase requests and confirm the title is the
subject, the 概要 says it once, a request without an about phrase is unchanged,
and a bare kind word still falls back.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentTitleNoAboutEchoResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_document_title_no_about_echo() -> DocumentTitleNoAboutEchoResult:
    from sidra_ai.creation.documents import _title_from, generate_document
    from sidra_ai.creation.evidence import Fact

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # 1: 「…についてのレポート」 titles the report by its subject only.
    add(_title_from("広告方針についてのレポートを作って") == "広告方針",
        f"について kept: 「{_title_from('広告方針についてのレポートを作って')}」")

    # 2: the rendered 概要 says the subject once, not 「…について」について.
    facts = [Fact("広告は第三者 JS を使わない。", "tukemen-rgb/site docs/ads.md")]
    md = generate_document("広告方針についてのレポートを作って", facts=facts).markdown
    add("「広告方針」について" in md and "広告方針について」について" not in md,
        "概要 doubles について")

    # 3: 「に関する」 is dropped too.
    add(_title_from("売上に関するレポートを作って") == "売上",
        f"に関する kept: 「{_title_from('売上に関するレポートを作って')}」")

    # 4: 「についての」 (with trailing の) is dropped.
    add(_title_from("新機能についてのドキュメントを作って") == "新機能",
        f"についての kept: 「{_title_from('新機能についてのドキュメントを作って')}」")

    # 5: a request with no about phrase is unchanged (C-1246 still holds).
    add(_title_from("競合分析のレポートを作って") == "競合分析",
        "a non-about title changed")

    # 6: a bare kind word still falls back, not emptied by the about strip.
    add(bool(_title_from("レポートを作って").strip()),
        "bare kind word produced an empty title")

    # 7: 「について」 mid-phrase (part of the subject, not the tail) is kept.
    add(_title_from("AIについての誤解の分析を作って") == "AIについての誤解の分析",
        f"mid-phrase について stripped: 「{_title_from('AIについての誤解の分析を作って')}」")

    return DocumentTitleNoAboutEchoResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=7,
        failures=tuple(failures),
    )


__all__ = ["DocumentTitleNoAboutEchoResult", "evaluate_document_title_no_about_echo"]
