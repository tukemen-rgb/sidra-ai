"""Reviewer's tool: prove the board still says what it means.

`docs/BACKLOG.md` is written by three loops at once, and the thing that
keeps breaking is not the prose but the *shape*: a completion record ends
up under someone else's item, or a block gets pasted twice. Between
2026-09-06 04:08 and 13:39 that needed six hand repairs
(`b835209` `832bad0` `ff24e9e` `b3a233a` `2099b44` `01c68e4`), and a
seventh case was live on the board when this check was written.

Six repairs read back, the damage takes exactly two shapes:

1. **A block appears twice.**  A claim is written, a rebase brings the
   other loop's copy back, and both survive (`832bad0` removed three such
   blocks; `b835209` and `b3a233a` one each).
2. **A record lands on the item below.**  A record is appended to an item's
   brief, a new item is inserted between the brief and the record, and the
   record is now part of the new item (`ff24e9e` `2099b44` `01c68e4`, four
   loops running, plus C-1446's record sitting under C-1447 when this file
   was added). `ff24e9e`'s own commit message names the cause.

So this checks two invariants, one per shape, and nothing else:

* a C number heads at most one item, and
* an item that is not finished carries no completion record.

    python scripts/check_backlog_board.py [path]

Exit 0 when the board is consistent, 1 when it is not. The report names
the line to look at, because the repair is always manual.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BOARD = Path(__file__).resolve().parents[1] / "docs" / "BACKLOG.md"

# An item heading. The board writes the state in the box and then, for
# finished work, the receipt *in front of* the title:
#   - [ ] **C-1447: ...**
#   - [~] 作業中 2026-09-06 14:12 UTC ループA **C-1447: ...**
#   - [x] 完了 ... (`metric` 8→9、判定器 exit 0) **C-1438: ...**
HEADING = re.compile(r"^- \[( |x|~|記録)\] ")
# The number that heads the item: the first bold **C-NNNN:** on the line.
# Records quote other C numbers freely, so only the bold-and-colon form -
# the way a title is written - counts as heading one.
HEADS = re.compile(r"\*\*(C-\d+)[:：]")
# A record appended under an item, as its own indented paragraph.
RECORD = re.compile(r"^\s+\*\*(記録|結果)[ 　]")
FINISHED = ("x", "記録")

# One collision predates the check and is not a drift: C-1011 was spent
# twice, on 見下ろし型アドベンチャー (completed 2026-08-29, line ~2177) and
# on 社長役 20 問 (line ~6740). Both numbers are quoted by finished records
# in LOOP_LOG.md and OUTCOMES.md and by comments in games.py / projects.py,
# so renumbering either would falsify somebody's finished record. It is
# listed rather than tolerated silently: any *other* repeat still fails.
KNOWN_COLLISIONS = {"C-1011"}


def read_items(text: str) -> list[dict]:
    """Every item on the board, with its box, its number and its body."""
    items: list[dict] = []
    for number, line in enumerate(text.split("\n"), start=1):
        head = HEADING.match(line)
        if head:
            number_match = HEADS.search(line)
            items.append(
                {
                    "line": number,
                    "box": head.group(1),
                    "id": number_match.group(1) if number_match else None,
                    "text": line,
                    "body": [],
                }
            )
        elif items:
            items[-1]["body"].append((number, line))
    return items


def check(text: str) -> list[str]:
    """Both invariants, in the order the repairs found them."""
    items = read_items(text)
    problems: list[str] = []

    seen: dict[str, int] = {}
    for item in items:
        if item["id"] is None:
            # Items older than the numbering scheme. They are titled, not
            # numbered, so there is nothing to collide.
            continue
        first = seen.get(item["id"])
        if first is not None and item["id"] not in KNOWN_COLLISIONS:
            problems.append(
                f"L{item['line']}: {item['id']} already heads the item at "
                f"L{first} - one number, two items (a block pasted twice, or "
                f"a claim that did not replace the line it claimed)"
            )
        seen.setdefault(item["id"], item["line"])

    for item in items:
        if item["box"] in FINISHED:
            continue
        for line_number, line in item["body"]:
            if RECORD.match(line):
                name = item["id"] or item["text"][:40]
                problems.append(
                    f"L{line_number}: a 記録/結果 block sits under {name}, "
                    f"which is still 「{item['box'] or ' '}」 at L{item['line']} "
                    "- an unfinished item cannot have a completion record, so "
                    "this record belongs to the item above it"
                )
                break

    return problems


def main(argv: list[str]) -> int:
    board = Path(argv[1]) if len(argv) > 1 else BOARD
    text = board.read_text(encoding="utf-8")
    problems = check(text)
    items = read_items(text)
    numbered = sum(1 for item in items if item["id"])
    if problems:
        print(f"{board}: {len(problems)} 件の不整合")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"{board}: {len(items)} 項目（うち採番 {numbered}）・不整合なし")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
