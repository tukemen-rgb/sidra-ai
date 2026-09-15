"""C-1865: plain_text keeps an empty table cell so columns stay aligned.

A follow-through to C-1226. _flatten_table_row dropped empty cells, shifting
every cell after a blank one left, so a value lined up under the wrong header.
Empty cells now hold their slot; an all-empty row still collapses to nothing.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.evidence import plain_text
from sidra_ai.evals.table_row_keeps_empty_cells import (
    evaluate_table_row_keeps_empty_cells,
)


def test_table_empty_cell_eval_passes():
    result = evaluate_table_row_keeps_empty_cells()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_blank_interior_cell_holds_its_slot():
    assert plain_text("| A |  | 100 |") == "A / / 100；"


def test_row_with_blank_cell_stays_aligned_with_its_header():
    out = plain_text("| 名前 | 状態 | 値 |\n|---|---|---|\n| A |  | 100 |\n| B | 稼働 | 5 |")
    assert out == "名前 / 状態 / 値； A / / 100； B / 稼働 / 5；"
    assert "A / 100；" not in out  # the buggy re-columned form


def test_all_empty_row_collapses_to_nothing():
    assert plain_text("|  |  |") == ""


def test_table_without_blank_cells_unchanged():
    assert plain_text("| 項目 | 値 |\n|---|---|\n| 売上 | 1,234 |") == "項目 / 値； 売上 / 1,234；"
