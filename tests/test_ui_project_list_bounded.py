"""C-1268: the entry page caps the projects list too.

C-1252 bounded loadArtifacts, but loadProjects kept rendering every production
with a bare items.forEach and no count note - the same phone long-scroll, on
the projects section. It now renders a newest-first slice bounded by
PROJECT_LIMIT and reports the total when there are more.
"""

from __future__ import annotations

import re

from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.ui_project_list_bounded import (
    evaluate_ui_project_list_bounded,
)


def _loadprojects_body() -> str:
    start = ASK_PAGE.find("function loadProjects()")
    assert start >= 0, "loadProjects not found"
    return ASK_PAGE[start : ASK_PAGE.find("\n  function ", start)]


def test_ui_project_list_bounded_eval_passes():
    result = evaluate_ui_project_list_bounded()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 4


def test_limit_is_declared_and_small():
    m = re.search(r"PROJECT_LIMIT\s*=\s*(\d+)", ASK_PAGE)
    assert m, "PROJECT_LIMIT not declared"
    assert 1 <= int(m.group(1)) <= 50


def test_render_uses_bounded_slice_not_full_list():
    body = _loadprojects_body()
    assert ".slice(0, PROJECT_LIMIT)" in body
    assert "shown.forEach(" in body
    # the full items array is no longer iterated in loadProjects
    assert "items.forEach(" not in body


def test_total_is_surfaced_when_capped():
    body = _loadprojects_body()
    assert "items.length" in body
    assert "PROJECT_LIMIT" in body
    assert "全 " in body and "件" in body
