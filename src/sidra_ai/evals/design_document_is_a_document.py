"""Does 設計書 reach the generator that writes documents?

C-1809. 仕様書, 要件定義書, 提案書, 報告書, 議事録 and マニュアル all route to
DOCUMENT; 設計書 did not, so 「設計書を作って」 was answered 「この形式は作れません。
いま作れるのは … レポート …」 - a document request declined by a sentence naming
the generator that would have written it, which is C-1804's shape one kind
along. A design document about indexed code is exactly what this generator
produces from evidence.

企画書 and 計画書 were measured in the same cycle and deliberately left alone.
The DOCUMENT cue list excludes business-plan wording to hold C-1263's boundary,
and the case that note pins is 「事業計画書」 - a business plan, which a
generator writing only from indexed evidence cannot honestly produce. That
exclusion is asserted here rather than merely avoided, so this change is
measured as *not* having reached it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DesignDocumentResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_design_document_is_a_document() -> DesignDocumentResult:
    from sidra_ai.creation.intent import CreationKind, detect_creation_intent

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    def kind_of(message: str):
        found = detect_creation_intent(message)
        return found.kind if found else None

    # --- (A) the one that was missing now reaches the writer --------------
    for request in ("設計書を作って", "ゲームの設計書を作って", "基本設計書を作って"):
        got = kind_of(request)
        add(got is CreationKind.DOCUMENT, f"A: 「{request}」 is {got}, not DOCUMENT")

    # --- (B) its siblings still do ----------------------------------------
    for request in ("仕様書を作って", "要件定義書を作って", "提案書を作って", "議事録を作って"):
        got = kind_of(request)
        add(got is CreationKind.DOCUMENT, f"B: 「{request}」 regressed to {got}")

    # --- (C) the business-plan exclusion is NOT reached --------------------
    # C-1263's line. 「事業計画書」 is the case it pins: a plan written from
    # nothing is not what an evidence-grounded generator makes, so these must
    # stay declined rather than answered with a hollow document.
    for request in ("事業計画書を作って", "企画書を作って", "計画書を作って"):
        got = kind_of(request)
        add(got is not CreationKind.DOCUMENT, f"C: 「{request}」 crossed C-1263's line into {got}")

    # --- (D) the production bundle is untouched ---------------------------
    for request in ("企画書一式を作って", "ゲームを企画から作って"):
        got = kind_of(request)
        add(got is CreationKind.PROJECT, f"D: 「{request}」 left PROJECT for {got}")

    return DesignDocumentResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = ["DesignDocumentResult", "evaluate_design_document_is_a_document"]
