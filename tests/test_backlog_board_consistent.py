"""The board must not lose a record to the item below it (C-1447).

`docs/BACKLOG.md` is appended to by three loops at once. Between
2026-09-06 04:08 and 13:39 six commits did nothing but put the board back
together by hand - and a seventh case was live when this test was written
(C-1446's record was sitting under C-1447, the very item that filed for
this check).

The repairs read back into exactly two shapes, and the checker has one
invariant per shape. What is tested here is that each invariant fires on
the shape it was chosen for and stays quiet on the legitimate case that
looks like it - a finished item *does* carry a record, and a record *does*
quote other C numbers in its prose.

The real boards from history are exercised by the judge in
`scripts/product_metrics.py`, which has git to hand; the boards below are
built here so the test stays hermetic and fast.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_backlog_board.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_backlog_board", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


board = _load()


# A board in the shape the real one uses: a heading line, an indented
# brief, and for finished work a receipt in front of the title.
BRIEF = "      （起票の根拠）→ 動かす数字: some_metric unmeasurable→1"
RECORD = "      **記録 2026-09-06 13:32 ループA**（判定器 exit 1）"
RECORD_BODY = "      **実測**: 退けば無傷、留まれば被弾。"


def _board(*lines: str) -> str:
    return "\n".join(("## キュー", *lines, ""))


def test_the_real_board_is_consistent_right_now():
    # If this fails, the board needs a repair - not this test.
    assert board.check((ROOT / "docs" / "BACKLOG.md").read_text(encoding="utf-8")) == []


def test_the_script_exits_zero_on_the_real_board():
    run = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=120
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert "不整合なし" in run.stdout


def test_the_script_exits_one_and_names_the_line(tmp_path):
    broken = tmp_path / "board.md"
    broken.write_text(
        _board(
            "- [記録] 完了 2026-09-06 **C-1446: 表の記述を実測で直す。**",
            BRIEF,
            "- [ ] **C-1447: 記録の誤着地を止める。**",
            BRIEF,
            RECORD,
            RECORD_BODY,
        ),
        encoding="utf-8",
    )
    run = subprocess.run(
        [sys.executable, str(SCRIPT), str(broken)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 1
    # The repair is manual, so the report has to say where to look.
    assert "L6" in run.stdout and "C-1447" in run.stdout


# --- shape 1: a record lands on the item below -------------------------
#
# ff24e9e / 2099b44 / 01c68e4, plus the live C-1446 case. A record is
# appended to an item's brief; a new item is then inserted between the
# brief and the record; the record is now part of the new item.


@pytest.mark.parametrize("box", [" ", "~"])
def test_a_record_under_an_unfinished_item_is_the_drift(box):
    text = _board(
        "- [記録] 完了 2026-09-06 **C-1446: 表の記述を実測で直す。**",
        BRIEF,
        f"- [{box}] **C-1447: 記録の誤着地を止める。**",
        BRIEF,
        RECORD,
        RECORD_BODY,
    )
    problems = board.check(text)
    assert len(problems) == 1
    assert "C-1447" in problems[0] and "記録" in problems[0]


def test_the_same_board_repaired_is_quiet():
    # The repair moves the record back above the inserted item. Nothing
    # else changes - so if this still failed, the check would be flagging
    # the insertion rather than the drift.
    text = _board(
        "- [記録] 完了 2026-09-06 **C-1446: 表の記述を実測で直す。**",
        BRIEF,
        RECORD,
        RECORD_BODY,
        "- [ ] **C-1447: 記録の誤着地を止める。**",
        BRIEF,
    )
    assert board.check(text) == []


def test_a_finished_item_carrying_a_record_is_the_normal_case():
    # Every completed item on the board has one. If this fired, the check
    # would demand the board delete its own evidence.
    for box in ("x", "記録"):
        text = _board(
            f"- [{box}] 完了 2026-09-06 **C-1446: 表の記述を実測で直す。**",
            BRIEF,
            RECORD,
            RECORD_BODY,
        )
        assert board.check(text) == [], box


def test_a_record_is_only_a_record_when_it_opens_the_paragraph():
    # Records quote each other constantly ("C-1349 の記録どおり"). A rule
    # that matched the word anywhere would fire on half the board.
    text = _board(
        "- [ ] **C-1447: 記録の誤着地を止める。**",
        "      根拠: C-1441 の**記録**にあるとおり、幕の検査は 1 枚しか見ない。",
        "      過去の**結果**を読み直して不変条件を選ぶ。",
    )
    assert board.check(text) == []


# --- shape 2: a block appears twice ------------------------------------
#
# 832bad0 removed three duplicated blocks; b835209 and b3a233a one each.
# The cause is a rebase bringing another loop's copy of a claim back.


def test_one_number_heading_two_items_is_the_duplicate():
    text = _board(
        "- [~] 作業中 2026-09-06 06:55 UTC 辛口クリエイター **C-1357: 怪獣は目覚めない。**",
        BRIEF,
        "- [~] 作業中 2026-09-06 07:30 UTC 辛口クリエイター **C-1357: 怪獣は目覚めない。**",
        BRIEF,
    )
    problems = board.check(text)
    assert len(problems) == 1
    assert "C-1357" in problems[0]


def test_a_claim_that_replaced_its_own_line_is_quiet():
    # The same commit, done right: one line, rewritten in place.
    text = _board(
        "- [~] 作業中 2026-09-06 07:30 UTC 辛口クリエイター **C-1357: 怪獣は目覚めない。**",
        BRIEF,
    )
    assert board.check(text) == []


def test_a_number_quoted_inside_a_brief_does_not_head_an_item():
    # Briefs name their neighbours all the time. Only the bold-and-colon
    # title form counts as heading an item.
    text = _board(
        "- [ ] **C-1447: 記録の誤着地を止める。**",
        "      C-1442 と C-1443 の記録が隣に落ちた（C-1441 も同型）。",
        "- [ ] **C-1448: 別の話。**",
        "      **C-1447** の検査を使う。",
    )
    assert board.check(text) == []


def test_an_untitled_item_from_before_the_numbering_is_skipped():
    # 70 of the board's items predate C numbers. They are titled, not
    # numbered, so there is nothing to collide - and two of them saying
    # the same thing is not this bug.
    text = _board(
        "- [x] **索引の永続化。**プロセス再起動で消える。",
        "- [x] **索引の永続化。**プロセス再起動で消える。",
    )
    assert board.check(text) == []


# --- the one collision that predates the check -------------------------


def test_the_known_collision_is_exactly_one_and_is_real():
    assert board.KNOWN_COLLISIONS == {"C-1011"}
    text = (ROOT / "docs" / "BACKLOG.md").read_text(encoding="utf-8")
    heads = [item["id"] for item in board.read_items(text) if item["id"]]
    assert heads.count("C-1011") == 2, "the exception outlived what it excused"


def test_a_second_collision_still_fails():
    # The exception is a list, not a switch: any other repeat is caught.
    text = _board(
        "- [x] 完了 2026-08-29 **C-1011: 見下ろし型アドベンチャー。**",
        "- [x] **C-1011: 社長役 20 問がリポジトリに無い。**",
        "- [x] 完了 2026-09-06 **C-1446: 表の記述を実測で直す。**",
        "- [~] 作業中 2026-09-06 **C-1446: 表の記述を実測で直す。**",
    )
    problems = board.check(text)
    assert len(problems) == 1
    assert "C-1446" in problems[0] and "C-1011" not in problems[0]
