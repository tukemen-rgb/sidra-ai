"""Does the conversation UI clear the question box after a real answer?

C-1700. The entry page keeps a conversation (``turns``) and replays it, but the
submit handler only read ``#q`` - it never cleared it. After each answer the
prior question stayed in the box, so a follow-up needed a manual delete first,
and re-clicking send re-asked the same question as a follow-up to itself. The
handler now clears the question box on a real answer, and only then: a refusal or
error leaves the text in place so it can be edited and retried.

UI JavaScript cannot be executed in the judge, so the checks read the page source
and its structure: the clear exists in the success path (after the real-answer
gate, before ``.catch``), is absent from the error path, and the question is
still read - with the send re-enable and history recording left intact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UiClearQuestionResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_clears_question_after_answer() -> UiClearQuestionResult:
    from sidra_ai.api.ui import ASK_PAGE

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # Scope the structural checks to the submit handler; other functions
    # (download, loadArtifacts) have their own .catch blocks that would
    # otherwise be mistaken for the fetch's error path.
    handler_start = ASK_PAGE.find('form.addEventListener("submit"')
    handler = ASK_PAGE[handler_start:] if handler_start != -1 else ""

    clear_re = re.compile(r'getElementById\("q"\)\.value\s*=\s*""')
    clear = clear_re.search(handler)
    gate = handler.find("!result.refused")
    catch = handler.find(".catch(")

    # --- (A) the success path clears the question box ---
    add(clear is not None, "A: the question box is never cleared after a submit")

    # --- (B) the clear sits in the success path: after the real-answer gate
    #         and before the .catch handler ---
    add(clear is not None and gate != -1 and catch != -1
        and gate < clear.start() < catch,
        "B: the clear is not gated to the real-answer success path")

    # --- (C) the clear is not in the error path (a failed submit keeps the
    #         question so it can be edited and retried) ---
    err_region = handler[catch:] if catch != -1 else ""
    add(catch != -1 and not clear_re.search(err_region),
        "C: the question is cleared on error, losing the text")

    # --- (D) the question is still read from the box (no regression) ---
    add('getElementById("q").value.trim()' in ASK_PAGE,
        "D: the question is no longer read from the box")

    # --- (E) the send button is still re-enabled (no regression) ---
    add("send.disabled = false" in ASK_PAGE,
        "E: the send button re-enable regressed")

    # --- (F) history recording is still present (no regression) ---
    add("turns.push(" in ASK_PAGE, "F: history recording regressed")

    total = 6
    return UiClearQuestionResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["UiClearQuestionResult", "evaluate_ui_clears_question_after_answer"]
