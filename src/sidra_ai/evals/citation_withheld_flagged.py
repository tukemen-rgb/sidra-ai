"""Do the CLI and web UI show when a citation's excerpt was withheld?

C-1236: an ingestion-time redaction shows as 「一部秘匿」 (CLI) / 「（伏せ字あり）」
(web), but when the *output guard* blocks a whole excerpt at answer time the
service sets ``excerpt_withheld`` precisely so a reader can tell that apart from
an ordinary citation - and both interfaces dropped the distinction, showing the
withheld citation exactly like any other. service.py says the two are different
facts "an operator deciding whether to trust an answer needs to tell apart";
the UIs now surface a withheld mark beside the redacted one.

The CLI checks drive ``_print_citations`` with a withheld, a redacted and a
plain citation; the web checks read the served ``ASK_PAGE`` for the same
handling. Layout is not computed here - the page is verified by its source, the
way the other ui_* evals are.
"""

from __future__ import annotations

import io
import re
from contextlib import redirect_stdout
from dataclasses import dataclass

_REDACTED_MARK = "一部秘匿"
_WITHHELD_MARK = "抜粋を秘匿"


@dataclass(frozen=True)
class CitationWithheldResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _cli_line(citation: dict) -> str:
    from sidra_ai.api.ask_cli import _print_citations, _Stripped

    payload = {"citations": [citation]}
    out = io.StringIO()
    with redirect_stdout(out):
        _print_citations(payload, _Stripped())
    return out.getvalue()


def evaluate_citation_withheld_flagged() -> CitationWithheldResult:
    checks = 0
    failures: list[str] = []

    base = {"label": "S1", "citation": "repo@abc:docs/a.md"}

    # --- CLI ---
    withheld = _cli_line({**base, "excerpt_withheld": True, "redacted": False})
    if _WITHHELD_MARK in withheld:
        checks += 1
    else:
        failures.append("CLI: a withheld excerpt is not flagged")
    # Distinct from the redaction mark, so the two facts stay tellable apart.
    if _WITHHELD_MARK != _REDACTED_MARK and _REDACTED_MARK not in withheld:
        checks += 1
    else:
        failures.append("CLI: withheld and redacted marks are not distinct")

    redacted = _cli_line({**base, "redacted": True, "excerpt_withheld": False})
    if _REDACTED_MARK in redacted and _WITHHELD_MARK not in redacted:
        checks += 1
    else:
        failures.append("CLI: the redacted mark regressed")

    plain = _cli_line({**base, "redacted": False, "excerpt_withheld": False})
    if _REDACTED_MARK not in plain and _WITHHELD_MARK not in plain:
        checks += 1
    else:
        failures.append("CLI: a plain citation carries a mark it should not")

    # --- web UI (page source) ---
    from sidra_ai.api.ui import ASK_PAGE

    # The property is actually read in a branch - not merely named in a comment
    # (the comment says "excerpt_withheld", the code says "c.excerpt_withheld").
    if re.search(r"c\.excerpt_withheld", ASK_PAGE):
        checks += 1
    else:
        failures.append("web: the page never branches on c.excerpt_withheld")
    # The withheld branch carries its own visible text (ASK_PAGE is the loaded
    # value, so a \\u-escaped source still reads as the character here).
    if _WITHHELD_MARK in ASK_PAGE:
        checks += 1
    else:
        failures.append("web: no visible withheld mark on the page")
    # The redacted flag is still there (regression guard).
    if re.search(r"c\.redacted", ASK_PAGE):
        checks += 1
    else:
        failures.append("web: the redacted flag regressed")

    return CitationWithheldResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=7,
        failures=tuple(failures),
    )
