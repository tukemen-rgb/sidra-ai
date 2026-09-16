"""Does the web page strip terminal-control and bidi characters from DATA it shows?

C-1883, the browser twin of the CLI's C-1627. Retrieved content is DATA from
outside. The page inserts it with ``textContent``, which stops it being parsed as
markup - but a browser still ACTS on direction-changing and invisible characters
the way a terminal does: a bidi override (U+202E) or isolate (U+2066-2069)
reorders what the reader sees, so a citation excerpt can display in an order it
was not written in. The CLI removes these on output for exactly this reason
(``ask_cli._STRIPPED_CODEPOINTS``: "the gate can be widened and a terminal
cannot"), and the page had no equivalent.

It is reachable, not only defence in depth: measured through the real ingestion
gate, RLO/zero-width/BOM are quarantined, but the bidi ISOLATES (U+2066-2069), the
C1 controls (U+0080-009F) and ESC pass and reach the excerpt/answer the page then
renders. So the page strips the same set the CLI does, on every DATA insertion
(answer, repository/path, excerpt, source URL), and reports the count rather than
dropping characters silently.

UI JavaScript is not executed in the judge, so the checks read the page source:
each DATA insertion goes through ``clean``, ``clean`` covers each dangerous range,
and the removal is reported. A browser confirmation is run outside the judge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UiStripResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_strips_terminal_controls_from_evidence() -> UiStripResult:
    from sidra_ai.api.ui import ASK_PAGE

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    page = ASK_PAGE
    # The clean function that removes the codepoints, scoped for the range checks.
    fn_at = page.find("function clean(")
    fn = page[fn_at:fn_at + 900] if fn_at != -1 else ""

    # --- (A) the strip function exists ------------------------------------
    add(fn != "", "A: no clean() strip function on the page")

    # --- (B-D) every DATA insertion goes through clean() -------------------
    add(re.search(r"answer\.textContent\s*=\s*clean\(", page) is not None,
        "B: the answer body is inserted without clean()")
    add(re.search(r"evidence\.textContent\s*=\s*clean\(", page) is not None,
        "C: the citation excerpt is inserted without clean()")
    add(re.search(r"where\.textContent\s*=\s*clean\(", page) is not None,
        "D: the repository/path is inserted without clean()")

    # --- (E-I) clean() covers each dangerous range ------------------------
    low = fn.lower()
    add("0x2066" in low and "0x2069" in low, "E: bidi isolates (U+2066-2069) not stripped")
    add("0x202a" in low and "0x202e" in low, "F: bidi overrides (U+202A-202E) not stripped")
    add("0x9f" in low, "G: C1 controls (U+0080-009F) not stripped")
    add("0x200b" in low and "0xfeff" in low, "H: zero-width / BOM not stripped")
    add("0x09" in low and "0x0a" in low,
        "I: C0 controls not handled with tab/newline kept")

    # --- (J) the removal is reported, not silent (C-1627 parity) ----------
    add("_stripped" in page and ("制御文字" in page or "取り除い" in page),
        "J: characters are stripped silently, with no note to the reader")

    total = 10
    return UiStripResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["UiStripResult", "evaluate_ui_strips_terminal_controls_from_evidence"]
