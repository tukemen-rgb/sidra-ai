#!/usr/bin/env python3
"""A number this push claims must not already head somebody else's item (C-1800).

Each loop reads its own copy of the board, takes `max + 1`, writes a `[~] 確保`
line and starts working. Another loop's claim that has not been pushed yet is
not in that copy, so two loops take the same number. Measured across
`docs/LOOP_LOG.md` and `docs/BACKLOG.md` on 2026-09-14: 49 distinct numbers
appear in a renumbering record, 9 of them in the last ~28 hours - a count of
*records*, so read it as "at least".

Most of that is already caught. `check_backlog_board.py` refuses a board where
one number heads two items, and when both claims end up in one file - the
ordinary outcome, since every loop rebases - that is exactly what it sees.
Measured in a throwaway repository: the colliding push is refused today.

**One path escapes, and it is the worst one.** If the rebase is resolved by
keeping only our own line, the other loop's claim is gone; the board has no
duplicate, nothing refuses, and the push lands - deleting somebody else's claim
from `origin/main`. Measured the same way: push rc=0, and the other loop's item
no longer exists upstream. That is 厳守事項 5 ("do not delete another AI's work
without reason") happening by accident, silently.

So this compares the numbers that head items here against the ones that head
items on `origin/main`, and refuses when a number heads a *different* item in
each **and** the upstream item's title is nowhere in our board. The second
clause is what keeps an ordinary edit - `[ ]` to `[~]` to `[x]`, which keeps
the title - from being refused (C-1781 is the standing reminder of what a false
refusal costs). A deliberate retitling would trip it; that is rare, the message
says what it saw, and the cost of the alternative is somebody's work vanishing.

Numbers are read from item **headings** only, never from prose that mentions
one (禁じ手 ②), and nothing here renumbers anything: it refuses and leaves the
choice to the loop (禁じ手 ①).

When `origin/main` cannot be read, this passes with a note and **does not say
it checked** - the precedent is `check_log_times.py`, and the rule it must not
break is C-1723's: never print OK for something that was not read.

Exit 0 when clean or unreadable, 1 on a collision, 2 when the board itself
cannot be read.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_backlog_board import HEADS, read_items  # noqa: E402

BOARD = Path("docs/BACKLOG.md")

#: The title a heading gives its number: what follows `C-NNNN:` inside the
#: same bold run. Compared with whitespace collapsed, so a rewrap is not a
#: retitle.
TITLE = re.compile(r"\*\*C-\d+[:：]\s*(.*?)\*\*", re.S)


def _title(line: str) -> str:
    found = TITLE.search(line)
    return re.sub(r"\s+", " ", found.group(1)).strip() if found else ""


def headings(text: str) -> dict[str, str]:
    """Number -> title, for every item heading in a board."""

    out: dict[str, str] = {}
    for item in read_items(text):
        if item["id"] and item["id"] not in out:
            out[item["id"]] = _title(item["text"])
    return out


def _git(*args: str) -> subprocess.CompletedProcess:
    root = Path(__file__).resolve().parent.parent
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, timeout=120
    )


def collisions(here: dict[str, str], upstream: dict[str, str]) -> list[str]:
    """Numbers that head a different item in each board, with the upstream
    item's title gone from ours."""

    ours = {title for title in here.values() if title}
    found = []
    for number, title in sorted(here.items()):
        theirs = upstream.get(number)
        if theirs is None or not theirs:
            # No item upstream, or one whose title could not be read. Unknown
            # is not wrong; the filter below handles the identical-title case,
            # which is what an ordinary `[ ]`→`[~]`→`[x]` edit looks like.
            continue
        if theirs in ours:
            # Their item is still here under another number - somebody
            # renumbered, which is the fix, not the fault.
            continue
        found.append(
            f"{number} heads 「{title[:40]}」 here and 「{theirs[:40]}」 on "
            f"origin/main, and theirs is not on this board at all"
        )
    return found


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    board = root / BOARD
    if not board.is_file():
        print(f"REFUSED: {BOARD} is not there, so no number was read")
        return 2

    here = headings(board.read_text(encoding="utf-8"))
    if not here:
        print(f"REFUSED: no item headings in {BOARD}, so the scan read nothing")
        return 2

    fetched = _git("fetch", "-q", "origin", "main")
    shown = _git("show", "origin/main:docs/BACKLOG.md")
    if fetched.returncode != 0 or shown.returncode != 0:
        # Not a refusal, and deliberately not a clean bill of health either.
        print("NOTE: origin/main could not be read, so no number was compared")
        return 0

    found = collisions(here, headings(shown.stdout))
    if found:
        print(f"REFUSED: {len(found)} number(s) already head another item upstream")
        for line in found:
            print(f"  {line}")
        print("  Another loop claimed the number while this one was working, and")
        print("  its item is missing here - most likely dropped in a rebase.")
        print("  Take a fresh number for this item, or restore theirs. Do not")
        print("  renumber somebody else's line.")
        return 1
    print(f"{len(here)} numbered items: none collides with origin/main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
