"""Does the entry page cap how many projects it lists?

C-1268: ``loadArtifacts`` was bounded to a recent slice (C-1252), but
``loadProjects`` still rendered every project the API returned with
``items.forEach`` and no count note - the same phone long-scroll the artifact
cap fixed, on the projects list. It now shows a bounded slice and reports the
total.

Layout height cannot be computed offline, so the checks pin the cap on the page
source, mirroring the artifact check: a small numeric limit exists, the render
loop runs over a bounded slice, the total is surfaced when the list is longer
than the cap, and the loop no longer iterates the whole ``items`` array.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: A first screen shows a handful, not hundreds.
_SANE_MAX = 50


@dataclass(frozen=True)
class UiProjectListBoundedResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _load_projects_body(page: str) -> str:
    start = page.find("function loadProjects()")
    if start < 0:
        return ""
    rest = page[start + len("function loadProjects()") :]
    end = rest.find("\n  function ")
    return rest if end < 0 else rest[:end]


def evaluate_ui_project_list_bounded() -> UiProjectListBoundedResult:
    from sidra_ai.api.ui import ASK_PAGE

    body = _load_projects_body(ASK_PAGE)

    checks = 0
    failures: list[str] = []

    # 1: a numeric cap is declared and is a sane first-screen size.
    limit_match = re.search(r"PROJECT_LIMIT\s*=\s*(\d+)", ASK_PAGE)
    limit = int(limit_match.group(1)) if limit_match else None
    if limit is not None and 1 <= limit <= _SANE_MAX:
        checks += 1
    else:
        failures.append(f"no sane PROJECT_LIMIT (got {limit})")

    # 2: the render loop runs over a bounded slice, not the full list.
    if re.search(r"\.slice\(\s*0\s*,\s*PROJECT_LIMIT\s*\)", body) and ".forEach(" in body:
        checks += 1
    else:
        failures.append("loadProjects does not render a bounded slice")

    # 3: when the list is longer than the cap, the total is surfaced.
    if "items.length" in body and re.search(r"PROJECT_LIMIT", body) and (
        "全" in body or "他" in body
    ):
        checks += 1
    else:
        failures.append("the total count is not surfaced when the list is capped")

    # 4: the loop no longer iterates the whole `items` array directly.
    if not re.search(r"\bitems\.forEach\(", body):
        checks += 1
    else:
        failures.append("loadProjects still iterates the full items list")

    return UiProjectListBoundedResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=4,
        failures=tuple(failures),
    )


__all__ = ["UiProjectListBoundedResult", "evaluate_ui_project_list_bounded"]
