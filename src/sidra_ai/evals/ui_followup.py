"""Can a browser user ask a follow-up question at all?

C-1210: ``/v1/chat`` has carried screened, enveloped history since the
envelope work - and the ask page never sent it, so every browser follow-up
(「それはなぜ？」) retrieved nothing on its own words and got the honest
abstention. The capability existed; the one doorway employees use did not
reach it.

CSS/JS behaviour cannot be executed offline here, so the checks pin the
exact mechanics on the page source, both directions: the conversation array
is kept and bounded to the server's own cap, only successful exchanges join
it, the payload actually carries it, and the page's pinned storage posture
(no localStorage) survives. The end-to-end proof ran in a real browser at
fix time and lives in the loop log; these checks keep the mechanics from
quietly regressing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UiFollowupResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_followup() -> UiFollowupResult:
    from sidra_ai.api.schemas import MAX_HISTORY_TURNS
    from sidra_ai.api.ui import ASK_PAGE

    checks = 0
    failures: list[str] = []

    if "payload.history = turns.slice(-MAX_TURNS)" in ASK_PAGE:
        checks += 1
    else:
        failures.append("the request payload no longer carries the conversation")
    if "JSON.stringify(payload)" in ASK_PAGE:
        checks += 1
    else:
        failures.append("the payload is built but not what is sent")
    if f"MAX_TURNS = {MAX_HISTORY_TURNS};" in ASK_PAGE:
        checks += 1
    else:
        failures.append("the page's turn cap disagrees with the server's")
    if "!result.refused" in ASK_PAGE and "turns.push({ question: question, answer: result.answer })" in ASK_PAGE:
        checks += 1
    else:
        failures.append("exchanges join the conversation without the success guard")
    if "localStorage" not in ASK_PAGE:
        checks += 1
    else:
        failures.append("the conversation leaked into localStorage")

    return UiFollowupResult(
        passed=not failures, checks_passed=checks, checks_total=5,
        failures=tuple(failures),
    )
