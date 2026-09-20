"""C-1987: the size shown carries to the next unit when rounding reaches 1024.

``formatBytes`` (C-1895) scaled while ``value >= 1024`` and then rounded, so a
size just under a power of 1024 - ``1048064`` bytes is ``1023.5`` KB - read as
``"1024 KB"`` where a person expects ``"1.0 MB"``, and the same a byte under a
gigabyte read ``"1024 MB"``. The eval runs the page's own ``formatBytes`` in
node over the boundary sizes and over ordinary ones (which must not move).
"""

from __future__ import annotations

import shutil

import pytest

from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.ui_artifact_size_carries_at_unit_boundary import (
    _format_bytes_source,
    _run,
    evaluate_ui_artifact_size_carries_at_unit_boundary,
)

_HAS_NODE = shutil.which("node") is not None
_needs_node = pytest.mark.skipif(not _HAS_NODE, reason="node is unavailable")


@_needs_node
def test_ui_artifact_size_carries_at_unit_boundary_eval_passes():
    result = evaluate_ui_artifact_size_carries_at_unit_boundary()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total


@_needs_node
def test_boundary_sizes_carry_to_the_next_unit():
    got = _run(ASK_PAGE)
    # 1023.5 KB and one byte under a MB both read as a MB, not "1024 KB".
    assert got[0] == "1.0 MB"
    assert got[1] == "1.0 MB"
    # one byte under a GB reads as a GB, not "1024 MB".
    assert got[3] == "1.0 GB"
    assert not [g for g in got if g in ("1024 KB", "1024 MB", "1024 GB")]


@_needs_node
def test_ordinary_sizes_do_not_promote():
    got = _run(ASK_PAGE)
    # 1023.0 KB must stay KB - an over-eager carry would read "1.0 MB".
    assert "1023 KB" in got
    assert "107 KB" in got and "3.1 KB" in got and "2.3 MB" in got


def test_helper_source_is_extractable():
    assert _format_bytes_source(ASK_PAGE).startswith("function formatBytes(")
