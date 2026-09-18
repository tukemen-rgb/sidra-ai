"""Does the board's instrument see every number an item claims as its own?

C-1958. ``check_backlog_board.HEADS`` matched a number only where it stood
first inside a bold run - 「**C-1451: …」 - so an item written 「- [ ] **要判断:
C-1957: …」 claimed a number the instrument could not read. The collision
check runs on what the instrument reads, so two items both heading C-1957 sat
in main while the board printed 「不整合なし」.

**Measured before writing anything** (2026-09-18, on the real board): of every
bold run in the file that carries 「C-nnnn:」, the prefixes are 797 empty ones,
four 「要判断: 」, and two fragments of prose. So one labelled form exists, and
the repair is to read it - not to loosen the match.

**The obvious repair is the one the filing forbids**, and measuring says why:
finding the number anywhere in the line changes an id that was already right
(a line that quotes another item's number alongside its own). The repair here
is anchored instead - it runs only where the first form found nothing, so no
number the instrument already reads can move. That makes rule (D) structural
rather than lucky, which is why (D) is checked against a *rewritten* reader
rather than against a remembered count: a count would pass forever while the
reader quietly changed underneath it.

**What this counts.** Four sides, on boards built here rather than on the live
file. The live board is a moving target - the C-1957 pair this was filed for
is two owners' to resolve, and the day they do, a check pinned to it would go
green for the wrong reason. It is read as a *reading*, not as a side.

1. A number heads its item in each form the board actually uses: introduced
   by a short label (「**要判断: C-1957:」), and named with no bold run at all
   (「作業中 … 辛口ユーザー C-1961:」). The second was found live while this was
   being written - the board was printing that claim as 「L262」.
2. A number that is only mentioned does not. Three shapes: a body line that
   cites another item, a head line that quotes the labelled form in its
   reasoning before naming its own number, and - the one that has teeth - an
   **unnumbered** head line that quotes it. The first two are caught by the
   first form before the labelled one is ever reached, so a labelled form read
   loosely passes them both; only a line with no number of its own makes the
   loose reading answer, and answer wrongly.
3. Two items claiming one number are reported as 「one number, two items」,
   in both the plain and the labelled form.
4. Every id the old reader produced on the real board is unchanged.
5. A repeat somebody has decided about is **named** and does not refuse; one
   nobody has decided about still refuses. Both directions, because either
   alone is satisfied by an instrument that accepts everything or one that
   accepts nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: A board with one of each shape. Written as a whole file because the reader
#: takes a file: feeding it fragments would test a function this does not have.
_BOARD = """## 完了条件（2026-08-19 変更）

### A. 普通の項目

- [ ] **C-8001: a number standing first in the bold run.**〔小〕
      本文で C-8002 の原因に触れるが、これは参照であって名乗りではない。
      → 動かす数字: `example_number_one`

- [x] 完了 2026-09-18 10:00 UTC ループA（`example_number_two` 新設 0→1） **C-8002: a finished item.**〔小〕

- [~] 作業中 2026-09-18 10:30 UTC ループA　**確保時の判断**: 起票が \
`- [ ] **要判断: C-8009: …**` の形を引用しているが、**これは引用**であって \
この項目の身元ではない。 **C-8003: a claim that quotes the labelled form.**〔小〕
      → 動かす数字: `example_number_three`

- [~] 作業中 2026-09-18 辛口ユーザー C-8005: a number named with no bold run at all.
      → 動かす数字: `example_number_five`

- [ ] **古い項目（採番前のもの）** 参照: `- [ ] **要判断: C-8009: …**` \
の形が読めていない、という話をこの行がしている。
      この行は番号を名乗っていない——**引用しているだけ**。

### E. 判断が要る（実装せず、社長の判断を待つ）

- [ ] **要判断: C-8004: a number introduced by a label.**
      （2026-09-18 11:00 UTC 起票）
"""

#: The same board with one number spent twice - once in each form, so a repair
#: that reads only one of them scores half.
_COLLIDING = _BOARD.replace("**C-8001:", "**C-8002:").replace(
    "**要判断: C-8004:", "**要判断: C-8003:"
)


@dataclass(frozen=True)
class NumberedHeadResult:
    sides_right: int
    sides_total: int = 5
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def evaluate_board_sees_every_numbered_head() -> NumberedHeadResult:
    import importlib.util
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "_board_under_test", root / "scripts" / "check_backlog_board.py"
    )
    assert spec and spec.loader
    board = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(board)

    failures: list[str] = []
    readings: list[str] = []
    right = 0

    def ids(text: str) -> dict[str, int]:
        return {
            item["id"]: item["line"]
            for item in board.read_items(text)
            if item["id"]
        }

    seen = ids(_BOARD)

    # --- 1. the labelled form is read -----------------------------------
    problems = []
    if "C-8004" not in seen:
        problems.append("「**要判断: C-8004:」 heads no item")
    if "C-8005" not in seen:
        # The third form, found live on this board while this was written.
        problems.append("a number named with no bold run heads no item")
    if problems:
        failures.append("unusual heads: " + "; ".join(problems))
    else:
        right += 1
    readings.append(f"synthetic ids={sorted(seen)}")

    # --- 2. a mention is not a claim ------------------------------------
    problems = []
    if "C-8009" in seen:
        # The quoted form inside a claim's reasoning. This is the shape the
        # loose repair gets wrong, and the filing says its author hit it.
        problems.append("a quoted example was read as a head")
    if seen.get("C-8003") is None:
        problems.append("the claim that quotes one lost its own number")
    if "C-8002" in seen and seen["C-8002"] == seen.get("C-8001"):
        problems.append("a prose reference collapsed two items")
    if problems:
        failures.append("mention: " + "; ".join(problems))
    else:
        right += 1

    # --- 3. one number, two items is reported ---------------------------
    problems = []
    reported = board.check(_COLLIDING)
    for number in ("C-8002", "C-8003"):
        if not any(number in line and "one number, two items" in line
                   for line in reported):
            problems.append(f"{number} collides and was not reported")
    readings.append(f"collisions reported={len(reported)}")
    if problems:
        failures.append("collision: " + "; ".join(problems))
    else:
        right += 1

    # --- 4. nothing the old reader read has moved -----------------------
    #
    # Recomputed from the real board with the original expression, rather
    # than compared against a number written down here: a remembered count
    # goes on passing while the reader changes underneath it.
    problems = []
    live = (root / "docs" / "BACKLOG.md").read_text(encoding="utf-8")
    moved = 0
    for item in board.read_items(live):
        direct = board.HEADS.search(item["text"])
        if direct and item["id"] != direct.group(1):
            moved += 1
            if len(problems) < 2:
                problems.append(
                    f"L{item['line']}: {direct.group(1)} is now read as {item['id']}"
                )
    readings.append(f"live heads moved={moved}")
    if problems:
        failures.append(f"moved {moved}: " + "; ".join(problems))
    else:
        right += 1

    # --- 5. a settled repeat is named, not hidden, and not a refusal -----
    #
    # C-1957's two lines are staying. Its owner settled it in their own
    # completion line - a claim's headline is the item's identity and is not
    # rewritten after it is pushed - and one side is now a finished record,
    # so renumbering either would falsify it. That is what KNOWN_COLLISIONS
    # is for, and what it says of itself: 「listed rather than tolerated
    # silently」. It was not listed anywhere a reader could see, which is how
    # the board could print 「不整合なし」 over a repeat nobody had decided
    # about. Both directions, because either alone is satisfied by an
    # instrument that accepts everything or one that accepts nothing.
    problems = []
    was = board.KNOWN_COLLISIONS
    try:
        board.KNOWN_COLLISIONS = set()
        if len(board.check(_COLLIDING)) < 2:
            problems.append("an undecided repeat stopped refusing")
        if board.accepted_collisions(_COLLIDING):
            problems.append("an undecided repeat was reported as settled")
        board.KNOWN_COLLISIONS = {"C-8002"}
        left = board.check(_COLLIDING)
        if any("C-8002" in line for line in left):
            problems.append("a settled repeat still refuses the push")
        if not any("C-8003" in line for line in left):
            problems.append("settling one repeat let the other through")
        named = board.accepted_collisions(_COLLIDING)
        if not (len(named) == 1 and "C-8002" in named[0]):
            problems.append(f"the settled repeat was not named: {named}")
    finally:
        board.KNOWN_COLLISIONS = was
    readings.append(f"accepted named={len(board.accepted_collisions(_COLLIDING))}")
    if problems:
        failures.append("settled: " + "; ".join(problems))
    else:
        right += 1

    return NumberedHeadResult(
        sides_right=right,
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = ["NumberedHeadResult", "evaluate_board_sees_every_numbered_head"]
