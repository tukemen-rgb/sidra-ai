"""Does the board checker say how many items a loop could actually take?

C-1854: ``check_backlog_board.py`` runs on every push and printed 「795 項目
（うち採番 673）・不整合なし」. It had every input needed to answer the question
each loop actually asks - the sections, the boxes and the 「→ 動かす数字:」 lines
are all in the same file - and ``read_items`` recorded line/box/id/text/body and
never the section, so 手順 2's exclusions (E and F) lived entirely outside the
tool. Measured over ``docs/LOOP_LOG.md``: ``ループA no-op`` appears 139 times,
19 of them consecutive, each re-deriving the same sentence from a 2.7 MB board.

The three cases are the item's, and the fourth is the one its 禁じ手 names most
sharply - and the one whose absence would flatter the loop that built this:

* **A** a board with nothing takeable says so, naming zero;
* **B** a board with one takeable item counts it and names it, so an
  implementation that only ever prints zero fails;
* **C** items in E and F are not counted, so an implementation that counts
  every ``- [ ]`` fails;
* **D** **zero never fails the push.** An empty queue is a legitimate state of
  the board (厳守事項 7 says to stop, not to invent work). A check that went red
  on zero would make the process demand that somebody fill the queue - which is
  exactly the failure the loop instructions warn about.

The fifth is C-1864, and it is the one the first four missed:

* **E** an item that declares its number **on its own headline line** is
  counted. ``read_items`` puts that line in ``text`` and only the continuation
  lines in ``body``, and ``takeable`` read ``body`` alone - so the whole form
  was invisible. Measured on the real board: 382 items declare their number on
  a continuation line and **7 on the headline**, and the one open item among
  those seven, C-1624, had been reported as not-takeable for about thirty
  cycles. The loop recorded 「no-op キューが空」 each time, and the queue was
  not empty. The same blind spot reached the loop's own notes, which recorded
  that C-1624 "has no 「→ 動かす数字:」 line at all" - checked through ``body``,
  the same way.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

#: A board with one item in each position that matters. Only C-9002 is
#: takeable: it names a number and sits in an ordinary section.
_HEAD = """# 盤

### C. 試験用

- [x] 完了 2026-09-14 10:00 UTC ループA **C-9001: 済んだ仕事。**
"""

_TAKEABLE = """- [ ] **C-9002: 取れる項目。**
      → 動かす数字: `metric_takeable` unmeasurable→1。
"""

#: Not takeable, and each for its own reason.
_TAIL = """- [ ] **C-9003: 数字を決めていない項目。**
      → 動かす数字: **未定**（まだ決めていない）。
- [ ] **C-9004: 数字の行が無い項目。**
      本文だけがあって、動かす数字を名乗らない。

### E. 判断が要る（実装せず、社長の判断を待つ）

- [ ] **C-9005: 判断待ち。**
      → 動かす数字: `metric_in_e_section` unmeasurable→1。

### F. 積み残し（着手前に価値を再確認すること）

- [ ] **C-9006: 積み残し。**
      → 動かす数字: `metric_in_f_section` unmeasurable→1。
"""

#: The same takeable item, declaring its number where C-1624 declares it -
#: on the item's own line. Nothing else about it differs, so a checker that
#: counts one board and not the other is reading the line, not the item.
_TAKEABLE_INLINE = """- [ ] **C-9007: 見出し行で数字を名乗る項目。** 本文はここに続く。→ 動かす数字: `metric_inline` unmeasurable→1。
"""

_EMPTY_BOARD = _HEAD + _TAIL
_ONE_BOARD = _HEAD + _TAKEABLE + _TAIL
_INLINE_BOARD = _HEAD + _TAKEABLE_INLINE + _TAIL


@dataclass(frozen=True)
class BoardTakeableResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _run(root: Path, board: Path) -> tuple[str, int]:
    script = Path(__file__).resolve().parents[3] / "scripts" / "check_backlog_board.py"
    ran = subprocess.run(
        [sys.executable, str(script), str(board)],
        capture_output=True, text=True, cwd=root,
    )
    return ran.stdout, ran.returncode


def _boards() -> tuple[Path, Path, Path, Path]:
    from sidra_ai.evals.scratch import scratch_dir

    root = Path(scratch_dir(prefix="board-takeable-"))
    empty = root / "EMPTY.md"
    one = root / "ONE.md"
    inline = root / "INLINE.md"
    empty.write_text(_EMPTY_BOARD, encoding="utf-8")
    one.write_text(_ONE_BOARD, encoding="utf-8")
    inline.write_text(_INLINE_BOARD, encoding="utf-8")
    return root, empty, one, inline


def evaluate_board_names_takeable_count() -> BoardTakeableResult:
    root, empty, one, inline = _boards()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    empty_out, empty_code = _run(root, empty)
    one_out, one_code = _run(root, one)

    # A: nothing takeable, and the report says zero.
    add(
        "取れる項目 0 件" in empty_out,
        f"an empty queue is not named as zero: 「{empty_out.strip()[:140]}」",
    )

    # B: one takeable item is counted and named - an implementation that always
    # prints zero dies here.
    add(
        "取れる項目 1 件" in one_out and "C-9002" in one_out,
        f"the one takeable item is not counted and named: 「{one_out.strip()[:140]}」",
    )

    # C: E and F are excluded - an implementation that counts every 「- [ ]」
    # would report three on the empty board and four on the other.
    add(
        "C-9005" not in one_out and "C-9006" not in one_out,
        f"an item in E or F was counted as takeable: 「{one_out.strip()[:140]}」",
    )

    # D: zero prints, it does not refuse. 禁じ手 ②.
    add(
        empty_code == 0,
        f"an empty queue failed the check (exit {empty_code}) - a red zero would "
        "make the process demand that somebody fill the queue",
    )

    # E: the number may be declared on the item's own line (C-1864). This is
    # where C-1624 lives, and it was invisible: `read_items` splits an item
    # into its headline and its continuation lines, and only the latter were
    # searched.
    inline_out, _ = _run(root, inline)
    add(
        "取れる項目 1 件" in inline_out and "C-9007" in inline_out,
        "an item declaring its number on its own headline was not counted: "
        f"「{inline_out.strip()[:140]}」",
    )

    return BoardTakeableResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=5,
        failures=tuple(failures),
    )


__all__ = ["BoardTakeableResult", "evaluate_board_names_takeable_count"]
