"""C-1819: the board checker says which 「~」 are live, instead of only counting items.

The knowledge was already there - ``_stranded_claims`` has named the leftover
claims since C-1728 - and the output was one line. Three loops spent about 59
hours re-deriving the same sentence from prose (22 LOOP_LOG lines mention
C-1694 or C-1699, 19 of them inside a no-op explanation).

These pin the two rules that stop the cheap version (a report that hides
whatever it judges), the provenance of the age, and the fact that the report
comes out of both of ``main``'s exits.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_backlog_board import (  # noqa: E402
    _age,
    _claim_commit_times,
    claims_report,
)
from sidra_ai.evals.board_says_which_claims_are_live import (  # noqa: E402
    _BOARD,
    _UNCOMMITTED,
    _UNEXPLAINED,
    evaluate_board_says_which_claims_are_live,
)


def _checkout(tmp_path: Path, name: str, text: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    board = root / "BACKLOG.md"
    board.write_text(text, encoding="utf-8")
    for command in (
        ("init", "-q"),
        ("config", "user.email", "probe@example.invalid"),
        ("config", "user.name", "probe"),
        ("add", "BACKLOG.md"),
        ("commit", "-q", "-m", "board"),
    ):
        subprocess.run(["git", *command], cwd=root, check=True, capture_output=True)
    return board


def test_a_written_reason_is_what_makes_a_leftover_not_the_age(tmp_path) -> None:
    # Both claims are structurally stranded and both are old. Only one carries
    # 「この行は取り残しです」, and that is the only thing that may separate them.
    board = _checkout(tmp_path, "unexplained", _UNEXPLAINED)
    report = "\n".join(claims_report(board.read_text(encoding="utf-8"), board))
    live = report.split("取り残し（作業ではない")[0]
    assert "C-9004" in live, report
    assert "C-9003" not in live, report


def test_a_leftover_is_still_printed(tmp_path) -> None:
    board = _checkout(tmp_path, "kept", _BOARD)
    report = "\n".join(claims_report(board.read_text(encoding="utf-8"), board))
    assert "C-9003" in report
    assert "取り残し" in report


def test_the_age_comes_from_the_commit_not_the_line(tmp_path) -> None:
    # C-9005's line says 2026-09-01; its commit is seconds old.
    board = _checkout(tmp_path, "age", _BOARD)
    report = claims_report(board.read_text(encoding="utf-8"), board)
    line = next(row for row in report if "C-9005" in row)
    assert "確保から 0 分" in line, line


def test_an_uncommitted_claim_is_unknown_not_fresh(tmp_path) -> None:
    # git blames an uncommitted line on the all-zero sha and stamps it *now*.
    # Taken at face value a claim written hours ago but never pushed reads as
    # 0 分 forever, so it never comes up for the 30-minute takeover.
    board = _checkout(tmp_path, "pending", _BOARD)
    board.write_text(_BOARD + _UNCOMMITTED, encoding="utf-8")
    report = claims_report(board.read_text(encoding="utf-8"), board)
    line = next(row for row in report if "C-9006" in row)
    assert "経過不明" in line, line


def test_an_unknown_age_never_reads_as_a_number() -> None:
    assert "経過不明" in _age(None)
    assert "0 分" not in _age(None)


def test_a_line_git_cannot_place_is_none(tmp_path) -> None:
    board = _checkout(tmp_path, "blame", _BOARD)
    board.write_text(_BOARD + _UNCOMMITTED, encoding="utf-8")
    line = len((_BOARD + _UNCOMMITTED).rstrip("\n").split("\n"))
    assert _claim_commit_times(board, [line])[line] is None


@pytest.mark.parametrize(
    "text, name, expected", [(_BOARD, "ok", 0), (_UNEXPLAINED, "refused", 1)]
)
def test_the_report_comes_out_of_both_exits(
    tmp_path, text: str, name: str, expected: int
) -> None:
    board = _checkout(tmp_path, name, text)
    if name == "refused":
        # A stranding counts only when it survives two versions.
        board.write_text(text + "\n<!-- 第2版 -->\n", encoding="utf-8")
        subprocess.run(["git", "commit", "-qam", "again"], cwd=board.parent,
                       check=True, capture_output=True)
        board.write_text(text, encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_backlog_board.py"
    ran = subprocess.run([sys.executable, str(script), str(board)],
                         capture_output=True, text=True, cwd=board.parent)
    # Which exit matters: if the refused board quietly returned 0 this would
    # be one test of the happy path run twice.
    assert ran.returncode == expected, ran.stdout + ran.stderr
    assert "確保「~」" in ran.stdout, ran.stdout


def test_the_eval_passes() -> None:
    result = evaluate_board_says_which_claims_are_live()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
