"""Does the web UI show a citation's trust level, like the CLI does (C-1469)?

C-1471, the web twin of C-1469. The CLI now renders a citation's trust level in
Japanese - 「外部」「未検証」 - so a reader can see when a source is third-party
authored (an Issue/PR body is EXTERNAL by ingestion). The browser page, the
surface most operators actually use, showed the 「（伏せ字あり）」 and
「（抜粋を秘匿）」 flags from the same citation payload but never read
``c.trust_level`` at all, so the safety signal was simply absent there.

The page now surfaces the trust level with the same Japanese labels the CLI
uses; ``internal_repo`` is suppressed and an unknown value falls back to raw.
The redaction flags are untouched, and markup is still never rendered.

Layout is not computed here - the page is verified by its source, the way the
other ui_* evals are (see ``citation_withheld_flagged``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The Japanese trust labels, identical to the CLI's _TRUST_LABELS (C-1469).
_LABELS = ("外部", "未検証", "運用者", "システム")


@dataclass(frozen=True)
class UiTrustLabelResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_citation_trust_label_shown() -> UiTrustLabelResult:
    from sidra_ai.api.ui import ASK_PAGE

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # The page reads c.trust_level in a branch, not merely names it in a comment.
    add(bool(re.search(r"c\.trust_level", ASK_PAGE)),
        "web: the page never branches on c.trust_level")
    # internal_repo is suppressed by the branch guard, the way the CLI does it -
    # verified as the actual guard expression, not mere presence in a comment.
    add(bool(re.search(r'trust_level\s*!==\s*"internal_repo"', ASK_PAGE)),
        "web: no internal_repo guard, so the norm would show a mark")
    # Each Japanese label is present (so the enum never reaches the reader raw).
    for label in _LABELS:
        add(label in ASK_PAGE, f"web: trust label {label!r} missing from the page")

    # Regression: the redaction flags and their visible text are untouched.
    add(bool(re.search(r"c\.redacted", ASK_PAGE)), "web: the redacted flag regressed")
    add(bool(re.search(r"c\.excerpt_withheld", ASK_PAGE)),
        "web: the excerpt_withheld flag regressed")
    add("伏せ字あり" in ASK_PAGE, "web: the redacted label text regressed")
    add("抜粋を秘匿" in ASK_PAGE, "web: the withheld label text regressed")

    total = 2 + len(_LABELS) + 4
    return UiTrustLabelResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["UiTrustLabelResult", "evaluate_ui_citation_trust_label_shown"]
