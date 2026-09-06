"""Does the ask page announce its async updates to assistive technology?

C-1286: after a submit, the page rewrites #status (「問い合わせ中…」, an error, a
refusal) and #answer (the reply) with ``textContent``. Neither was a live region,
so a screen-reader user heard nothing when the reply arrived and had no way to
know it was there (WCAG 4.1.3 Status Messages). #status now carries
``role="status"`` (an implicit ``aria-live="polite"``) and #answer
``aria-live="polite"``, so both are announced.

The checks confirm the announced regions are exactly the ones the page's own JS
updates - a live attribute on an element nothing rewrites would announce nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def _open_tag(html: str, element_id: str) -> str:
    """The opening tag carrying id="<element_id>", or "" if absent."""
    match = re.search(rf"<[^>]*\bid=\"{re.escape(element_id)}\"[^>]*>", html)
    return match.group(0) if match else ""


@dataclass(frozen=True)
class AskPageAnnounceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ask_page_announces_async_updates() -> AskPageAnnounceResult:
    from sidra_ai.api.ui import ASK_PAGE

    html = ASK_PAGE
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    status_tag = _open_tag(html, "status")
    answer_tag = _open_tag(html, "answer")

    # 1: the status region is a live region (role="status" is an implicit
    #    aria-live="polite"), so 「問い合わせ中…」/errors/refusals are announced.
    #    A real politeness value, so aria-live="off" does not pass as one.
    _live = ('role="status"', 'aria-live="polite"', 'aria-live="assertive"')
    add(any(token in status_tag for token in _live),
        f"#status is not a live region: {status_tag!r}")

    # 2: the answer region is announced when the reply is written into it.
    add('aria-live="polite"' in answer_tag or 'aria-live="assertive"' in answer_tag,
        f"#answer is not a live region: {answer_tag!r}")

    # 3-4: the announced regions are the ones the JS actually rewrites - a live
    #      attribute on a static element would announce nothing. The page binds
    #      statusLine/answer by id and assigns their textContent.
    add('getElementById("status")' in html and "statusLine.textContent" in html,
        "the JS does not update #status by textContent")
    add('getElementById("answer")' in html and "answer.textContent" in html,
        "the JS does not update #answer by textContent")

    # 5: a refusal's message lands in an announced region (statusLine), not a
    #    silent one - the refusal path writes statusLine.textContent.
    add(html.count("statusLine.textContent") >= 2,
        "the refusal/error message does not reach the live status region")

    # 6: the page still works as a page - the form and its submit are intact, so
    #    the fix did not gut the element it annotated.
    add('<form id="ask">' in html and 'id="answer"' in html,
        "the ask form or answer region went missing")

    total = 6
    return AskPageAnnounceResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "AskPageAnnounceResult",
    "evaluate_ask_page_announces_async_updates",
]
