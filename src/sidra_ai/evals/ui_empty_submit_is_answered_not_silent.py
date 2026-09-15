"""Does an empty submit on the web page get an answer instead of silence?

C-1874. The entry page answers every "not a question" input with a next step -
a greeting, an ambiguous or unnamed request, a help query each get a sentence
telling the reader what to do (the ``refusalMsg`` map). The one exception was the
most basic mistake of all: the submit handler read the box, trimmed it, and on an
empty or whitespace-only value did ``return`` before any feedback. Clicking 送信
on a blank box did nothing at all - no request, no status line, no hint.

That silence is the odd one out on three counts: the service has a considered
``empty`` refusal (C-1515), the CLI names it (exit 2), and this page already
carries ``refusalMsg["empty"]`` - it just returned before reaching it. The fix
shows that same sentence in the ``role="status" aria-live="polite"`` region and
reuses the one source (``refusalMessage({refusal:"empty"})``) rather than a second
copy, so a premature or whitespace-only click is answered like every other
non-question, and a screen reader hears it.

UI JavaScript cannot run in the judge, so the checks read the page source and its
structure: the empty guard now writes the status region, from the single source,
and still returns without sending a request; the ``empty`` message the reuse
points at still exists; and the C-1700 real-answer behaviours are untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UiEmptySubmitResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_empty_submit_is_answered_not_silent() -> UiEmptySubmitResult:
    from sidra_ai.api.ui import ASK_PAGE

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # Scope to the submit handler, then to the empty-question guard block: from
    # `if (!question)` up to `send.disabled = true` (the first thing the real
    # path does). The guard sits entirely inside that window, so a statusLine
    # write found here is the guard's, not the later waiting-text writes.
    handler_start = ASK_PAGE.find('form.addEventListener("submit"')
    handler = ASK_PAGE[handler_start:] if handler_start != -1 else ""
    guard_start = handler.find("if (!question)")
    disable_at = handler.find("send.disabled = true", guard_start) if guard_start != -1 else -1
    guard = handler[guard_start:disable_at] if (guard_start != -1 and disable_at != -1) else ""

    # --- (A) the guard exists and still short-circuits with a return ---
    #     Match the statement `return;`, not the bare word: the guard's own
    #     comment contains "returned", so a loose substring would report a
    #     return even after the statement itself was deleted.
    add(guard != "", "A: the empty-question guard could not be located")
    add(re.search(r"\breturn\s*;", guard) is not None,
        "A: the empty guard no longer returns before sending a request")

    # --- (B) the guard now writes the status region (feedback, not silence) ---
    add("statusLine.textContent" in guard,
        "B: an empty submit still produces no status feedback")

    # --- (C) it reuses the single source, not a second copy of the sentence ---
    add(re.search(r'refusalMessage\(\s*\{\s*refusal:\s*"empty"\s*\}\s*\)', guard) is not None,
        "C: the empty guard does not reuse refusalMessage({refusal:'empty'})")

    # --- (D) the source it reuses actually exists in the refusal map ---
    add('empty:' in ASK_PAGE and 'refusalMessage' in ASK_PAGE,
        "D: refusalMessage or its 'empty' entry is missing")

    # --- (E) the status region is a live region (announced, not silent to AT) ---
    add('id="status"' in ASK_PAGE and 'role="status"' in ASK_PAGE
        and 'aria-live="polite"' in ASK_PAGE,
        "E: the status region is not an announced live region")

    # --- (F) no regression on the C-1700 real-answer path ---
    add(re.search(r'getElementById\("q"\)\.value\s*=\s*""', handler) is not None,
        "F: the real-answer clear (C-1700) regressed")
    add("send.disabled = false" in ASK_PAGE, "F: the send re-enable regressed")
    add('getElementById("q").value.trim()' in ASK_PAGE,
        "F: the question is no longer read and trimmed")

    return UiEmptySubmitResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = ["UiEmptySubmitResult", "evaluate_ui_empty_submit_is_answered_not_silent"]
