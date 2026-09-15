"""C-1854: the board checker counts what a loop could actually take.

``read_items`` recorded line/box/id/text/body and never the section, so 手順 2's
exclusions (E and F) lived outside the tool and every loop re-derived "the queue
is empty" by hand - 139 ``ループA no-op`` lines in ``docs/LOOP_LOG.md``, 19 of
them consecutive when this was filed.

The rule is 手順 2's and is not widened here: an item is takeable when it names
the number it will move and is not in E or F. Whether a prerequisite in its body
is met is deliberately not judged by the machine (禁じ手 ④).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_backlog_board import read_items, takeable, takeable_report  # noqa: E402
from sidra_ai.evals.board_names_takeable_count import (  # noqa: E402
    _EMPTY_BOARD,
    _ONE_BOARD,
    evaluate_board_names_takeable_count,
)

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_backlog_board.py"


def _ids(board: str) -> list[str]:
    return [item["id"] for item in takeable(read_items(board))]


def test_the_section_is_recorded_at_all() -> None:
    # The blind spot itself: without this every other rule here is unreachable.
    items = read_items(_ONE_BOARD)
    assert all("section" in item for item in items)
    assert any("E. 判断が要る" in item["section"] for item in items)


def test_only_the_item_that_names_a_number_outside_e_and_f_counts() -> None:
    assert _ids(_ONE_BOARD) == ["C-9002"]


def test_an_empty_queue_counts_zero() -> None:
    assert _ids(_EMPTY_BOARD) == []
    assert "取れる項目 0 件" in "\n".join(takeable_report(read_items(_EMPTY_BOARD)))


@pytest.mark.parametrize("missing", ["C-9003", "C-9004", "C-9005", "C-9006"])
def test_each_excluded_item_stays_excluded(missing: str) -> None:
    # 9003 has no decided number, 9004 no number line at all, 9005 is in E,
    # 9006 in F. Each for its own reason, so a change that drops one rule is
    # visible here rather than hidden behind another.
    assert missing not in _ids(_ONE_BOARD)


def test_the_count_names_the_item(tmp_path) -> None:
    report = "\n".join(takeable_report(read_items(_ONE_BOARD)))
    assert "取れる項目 1 件" in report
    assert "C-9002" in report


def test_zero_prints_and_does_not_refuse(tmp_path) -> None:
    # 禁じ手 ②. An empty queue is a legitimate state of the board; a red zero
    # would make the process demand that somebody fill it.
    board = tmp_path / "BACKLOG.md"
    board.write_text(_EMPTY_BOARD, encoding="utf-8")
    ran = subprocess.run([sys.executable, str(_SCRIPT), str(board)],
                         capture_output=True, text=True, cwd=tmp_path)
    assert ran.returncode == 0, ran.stdout
    assert "取れる項目 0 件" in ran.stdout


def test_the_eval_passes() -> None:
    result = evaluate_board_names_takeable_count()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total


def test_a_number_declared_on_the_item_own_line_is_counted() -> None:
    """C-1864: the form that was invisible.

    ``read_items`` puts an item's own line in ``text`` and only the
    continuation lines in ``body``, and ``takeable`` searched ``body``. On
    the real board 382 items declare their number on a continuation line and
    7 on the headline; the one open item among those seven, C-1624, was
    reported as not-takeable for about thirty cycles while the loop wrote
    「no-op キューが空」.
    """

    inline = (
        "# 盤\n\n### C. 試験用\n\n"
        "- [ ] **C-9007: 見出し行で数字を名乗る項目。** 本文が続く。"
        "→ 動かす数字: `metric_inline` unmeasurable→1。\n"
    )

    assert "C-9007" in _ids(inline), (
        "an item is not less takeable for declaring its number on its own "
        "line - under-reporting hides a live item, which is the direction "
        "takeable()'s own docstring refuses"
    )


def test_the_two_places_a_number_can_be_written_agree() -> None:
    """The same item, the number moved to a continuation line, reads alike."""

    head = "# 盤\n\n### C. 試験用\n\n"
    on_line = head + (
        "- [ ] **C-9008: 題。** → 動かす数字: `metric_same` unmeasurable→1。\n"
    )
    on_body = head + (
        "- [ ] **C-9008: 題。**\n"
        "      → 動かす数字: `metric_same` unmeasurable→1。\n"
    )

    assert _ids(on_line) == _ids(on_body) == ["C-9008"]
