"""C-1867: plain_text keeps a table cell whole when it holds a pipe.

A follow-through to C-1226/C-1865. _flatten_table_row split cells on every pipe,
so a pipe inside inline code (a CLI-reference table) or an escaped \\| broke one
cell into several and shifted the row's columns. Cells now split with
_split_table_cells, which honours backtick spans and \\|.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.evidence import plain_text
from sidra_ai.evals.table_cell_pipe_in_code import (
    evaluate_table_cell_pipe_in_code,
)


def test_table_cell_pipe_eval_passes():
    result = evaluate_table_cell_pipe_in_code()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


def test_pipe_inside_inline_code_stays_in_its_cell():
    out = plain_text("| コマンド | 説明 |\n|---|---|\n| `ps aux | grep x` | プロセス検索 |")
    assert out == "コマンド / 説明； ps aux | grep x / プロセス検索；"
    assert "ps aux / grep x /" not in out  # the buggy re-columned form


def test_escaped_pipe_is_literal_not_a_cell_break():
    assert plain_text("| x \\| y | z |") == "x | y / z；"


def test_empty_cell_still_holds_its_slot():
    assert plain_text("| A |  | 100 |") == "A / / 100；"


def test_ordinary_table_unchanged():
    assert plain_text("| 項目 | 値 |\n|---|---|\n| 売上 | 1,234 |") == "項目 / 値； 売上 / 1,234；"
