"""C-1252: the entry page caps the generated-file list.

loadArtifacts rendered every artifact (200 in the instance), so the page grew
to ~50,000px on a phone. It now renders a newest-first slice bounded by
ARTIFACT_LIMIT and reports the total when there are more. The iPhone-emulation
proof (document height ~50466px → ~2337px, 20 rows) ran at fix time.
"""

from __future__ import annotations

import re

from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.ui_artifact_list_bounded import (
    evaluate_ui_artifact_list_bounded,
)


def test_ui_artifact_list_bounded_eval_passes():
    result = evaluate_ui_artifact_list_bounded()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 4


def test_limit_is_declared_and_small():
    m = re.search(r"ARTIFACT_LIMIT\s*=\s*(\d+)", ASK_PAGE)
    assert m, "ARTIFACT_LIMIT not declared"
    assert 1 <= int(m.group(1)) <= 50


def test_render_uses_bounded_slice_not_full_list():
    assert ".slice(0, ARTIFACT_LIMIT)" in ASK_PAGE
    assert "shown.forEach(" in ASK_PAGE
    # within loadArtifacts specifically, the full items array is not iterated
    start = ASK_PAGE.find("function loadArtifacts()")
    body = ASK_PAGE[start : ASK_PAGE.find("\n  function ", start)]
    assert "items.forEach(" not in body


def test_total_is_surfaced_when_capped():
    # a note references the total (items.length) alongside the limit
    assert "items.length" in ASK_PAGE
    assert "全 " in ASK_PAGE and "件" in ASK_PAGE
