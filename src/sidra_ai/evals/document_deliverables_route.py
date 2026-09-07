"""Do common Japanese document requests build a document instead of a Q&A miss?

C-1458: the DOCUMENT vocabulary held only 文書/ドキュメント/記事/レポート/報告書, so
「議事録を作って」「マニュアルを作って」「提案書を作って」「仕様書を作って」 - ordinary
written-document requests - were classified UNKNOWN and answered as a retrieval
Q&A instead of building the grounded report the document generator produces
(the same drop C-1455 fixed for polite phrasing). These nouns now route to
DOCUMENT; a request that also names another kind still resolves by the
latest-match rule, and business-plan wording (企画/計画) is left out so the
C-1263 boundary with the game-production bundle is unmoved.

The checks call the real ``detect_creation_intent`` and read the route.
"""

from __future__ import annotations

from dataclasses import dataclass

# Document-deliverable requests that must route to the DOCUMENT generator.
_DOCS = (
    "会議の議事録を作って",
    "操作マニュアルを作って",
    "新機能の提案書を作って",
    "APIの仕様書を作って",
    "要件定義書を作って",
    "手順書を作って",
    "説明書を作って",
)


@dataclass(frozen=True)
class DocumentDeliverablesResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_document_deliverables_route() -> DocumentDeliverablesResult:
    from sidra_ai.creation.intent import CreationKind, detect_creation_intent

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for message in _DOCS:
        intent = detect_creation_intent(message)
        add(intent.routes and intent.kind is CreationKind.DOCUMENT,
            f"document request not routed to DOCUMENT: {message!r} "
            f"(routes={intent.routes}, kind={intent.kind.name})")

    # Controls: the existing document word still routes, an explanation question
    # stays a question, and business-plan wording keeps the C-1263 boundary
    # (it does not become a DOCUMENT).
    report = detect_creation_intent("新機能の報告書を作って")
    add(report.routes and report.kind is CreationKind.DOCUMENT,
        "the existing 報告書 route regressed")

    howto = detect_creation_intent("議事録の作り方を教えて")
    add(not howto.is_creation, "an explanation question was misread as creation")

    plan = detect_creation_intent("事業計画書を作って")
    add(plan.kind is not CreationKind.DOCUMENT,
        "business-plan wording crossed the C-1263 boundary into DOCUMENT")

    total = len(_DOCS) + 3
    return DocumentDeliverablesResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DocumentDeliverablesResult", "evaluate_document_deliverables_route"]
