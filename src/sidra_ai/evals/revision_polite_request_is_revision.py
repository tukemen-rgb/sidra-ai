"""Does a politely-phrased revision request route to the reviser?

C-1463 is the twin of C-1455 for revision. ``detect_revision_intent`` shared the
creation detector's 「ますか」 question-marker veto, so a polite request to change
an existing game - 「さっきのゲームをもっと難しくしてもらえますか」「…していただけますか」
- was treated as a question and fell to the RAG no-evidence wall instead of
adjusting the game. A change stem plus a benefactive/honorific auxiliary is now
recognised as a request, exempt from the veto unless it is also an explanation
question.

The checks call the real ``detect_revision_intent``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Polite revision requests that must route (each carries a concrete adjustment).
_REQUESTS = (
    "さっきのゲームをもっと難しくしてもらえますか",
    "前のゲームを簡単にしてもらえますか",
    "さっきのを難しくしていただけますか",
    "今のゲームを紙の配色にしてもらえますか",
    "前のゲームを難しくしてください",
)

# Must NOT be read as a revision: a creation, a plain question, and an
# explanation question dressed as a polite request.
_NOT_REVISIONS = (
    "難しいゲームを作ってください",
    "難易度はどうやって変えるの",
    "難易度の変え方を教えてもらえますか",
)


@dataclass(frozen=True)
class RevisionPoliteResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_revision_polite_request_is_revision() -> RevisionPoliteResult:
    from sidra_ai.creation.revise import detect_revision_intent

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for message in _REQUESTS:
        intent = detect_revision_intent(message)
        add(intent.is_revision and bool(intent.adjustments),
            f"polite revision request not routed: {message!r} "
            f"(is_revision={intent.is_revision}, adjustments={intent.adjustments})")

    for message in _NOT_REVISIONS:
        intent = detect_revision_intent(message)
        add(not intent.is_revision,
            f"a non-revision was read as a revision: {message!r}")

    total = len(_REQUESTS) + len(_NOT_REVISIONS)
    return RevisionPoliteResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["RevisionPoliteResult", "evaluate_revision_polite_request_is_revision"]
