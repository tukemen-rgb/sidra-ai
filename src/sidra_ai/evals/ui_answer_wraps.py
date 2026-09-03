"""Does the answer stay inside a phone's viewport?

C-1214: the answer block had ``white-space: pre-wrap`` and no
``overflow-wrap``, so a citation label like
``tukemen-rgb/site@0eedf95:docs/competitive-analysis.md`` widened the
document from 390px to 401px on an iPhone-sized screen - and mobile
browsers respond by shrinking every glyph on the page to fit. The `.path`
class had already made this exact call; the answer body and the status
line now make it too.

Layout cannot be computed offline, so the checks pin the mechanics on the
page source; the end-to-end proof (scrollWidth staying at the viewport
width after an answer) ran in a real mobile emulation at fix time and is
recorded in the loop log.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UiAnswerWrapsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _rule_body(page: str, selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", page)
    return match.group(1) if match else ""


def evaluate_ui_answer_wraps() -> UiAnswerWrapsResult:
    from sidra_ai.api.ui import ASK_PAGE

    checks = 0
    failures: list[str] = []

    answer = _rule_body(ASK_PAGE, "#answer")
    if "overflow-wrap: anywhere" in answer:
        checks += 1
    else:
        failures.append("#answer no longer wraps long tokens")
    if "white-space: pre-wrap" in answer:
        checks += 1
    else:
        failures.append("#answer lost pre-wrap (line structure of answers)")

    if "overflow-wrap: anywhere" in _rule_body(ASK_PAGE, "#status"):
        checks += 1
    else:
        failures.append("#status no longer wraps long error text")

    if "overflow-wrap: anywhere" in _rule_body(ASK_PAGE, ".path"):
        checks += 1
    else:
        failures.append(".path lost its wrap (citation lists)")

    return UiAnswerWrapsResult(
        passed=not failures, checks_passed=checks, checks_total=4,
        failures=tuple(failures),
    )
