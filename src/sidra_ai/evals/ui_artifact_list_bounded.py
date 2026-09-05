"""Does the entry page cap how many generated files it lists?

C-1252: ``loadArtifacts`` rendered every artifact the API returned - 200 in the
running instance - so the page grew to ~50,000px on a phone: an endless scroll
that buries the projects section below it. The list is newest-first, and a
reader wants the recent handful; the rest is noise on the first screen.

Layout height cannot be computed offline, so the checks pin the cap on the page
source: a small numeric limit exists, the render loop runs over a bounded slice
rather than the whole list, and when there are more than the limit the status
line reports the total so nothing is hidden silently. The iPhone-emulation
proof (document height bounded) runs at fix time and is recorded in the loop
log.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: A first screen shows a handful, not hundreds. Anything above this is not a
#: "recent files" list any more.
_SANE_MAX = 50


@dataclass(frozen=True)
class UiArtifactListBoundedResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _load_artifacts_body(page: str) -> str:
    # The function body from `function loadArtifacts()` to the next top-level
    # `function ` at the same indentation - enough to scope the checks.
    start = page.find("function loadArtifacts()")
    if start < 0:
        return ""
    rest = page[start + len("function loadArtifacts()") :]
    end = rest.find("\n  function ")
    return rest if end < 0 else rest[:end]


def evaluate_ui_artifact_list_bounded() -> UiArtifactListBoundedResult:
    from sidra_ai.api.ui import ASK_PAGE

    body = _load_artifacts_body(ASK_PAGE)

    checks = 0
    failures: list[str] = []

    # 1: a numeric cap is declared and is a sane first-screen size.
    limit_match = re.search(r"ARTIFACT_LIMIT\s*=\s*(\d+)", ASK_PAGE)
    limit = int(limit_match.group(1)) if limit_match else None
    if limit is not None and 1 <= limit <= _SANE_MAX:
        checks += 1
    else:
        failures.append(f"no sane ARTIFACT_LIMIT (got {limit})")

    # 2: the render loop runs over a bounded slice, not the full list.
    if re.search(r"\.slice\(\s*0\s*,\s*ARTIFACT_LIMIT\s*\)", body) and ".forEach(" in body:
        checks += 1
    else:
        failures.append("loadArtifacts does not render a bounded slice")

    # 3: when the list is longer than the cap, the total is surfaced - the
    # hidden ones are reported, not dropped silently.
    if "items.length" in body and re.search(r"ARTIFACT_LIMIT", body) and (
        "全" in body or "他" in body
    ):
        checks += 1
    else:
        failures.append("the total count is not surfaced when the list is capped")

    # 4: the loop no longer iterates the whole `items` array directly (a bounded
    # variable is what gets rendered).
    if not re.search(r"\bitems\.forEach\(", body):
        checks += 1
    else:
        failures.append("loadArtifacts still iterates the full items list")

    return UiArtifactListBoundedResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=4,
        failures=tuple(failures),
    )


__all__ = ["UiArtifactListBoundedResult", "evaluate_ui_artifact_list_bounded"]
