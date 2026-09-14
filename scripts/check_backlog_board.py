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
# The stamp a record and its item's completion both carry: the same hand
# wrote them in the same commit, so a correctly placed pair always agrees.
#   - [x] 完了 2026-09-06 22:34 UTC ループA（...） **C-1451: ...**
#         **記録 2026-09-06 22:34 ループA**（...）
STAMP = re.compile(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})[^（(]*?(ループA|ループB|辛口[^\s（(]*|進捗監視|対話セッション)")
# The metric an item exists to move, and any metric name quoted in prose.
# The 「→ 動かす数字:」 label and its name are routinely on different lines,
# because the briefs are hand-wrapped; ``\s*`` spans the wrap, which is the
# whole reason this reads the item as a block of text rather than line by
# line. (Measured: replacing the join with the file as written changes no
# result - the newline was already inside ``\s``. It is written down here
# rather than defended by a test that would pass either way.)
MOVES = re.compile(r"→\s*動かす数字[:：]\s*`?([a-z][a-z0-9_]{6,})`?")
QUOTED = re.compile(r"`([a-z][a-z0-9_]{6,})`")
FINISHED = ("x", "記録")

# One collision predates the check and is not a drift: C-1011 was spent
# twice, on 見下ろし型アドベンチャー (completed 2026-08-29, line ~2177) and
# on 社長役 20 問 (line ~6740). Both numbers are quoted by finished records
# in LOOP_LOG.md and OUTCOMES.md and by comments in games.py / projects.py,
# so renumbering either would falsify somebody's finished record. It is
# listed rather than tolerated silently: any *other* repeat still fails.
KNOWN_COLLISIONS = {"C-1011"}


#: C-1728: a claim line left behind by a renumbering. When a claim's number
#: is reassigned, the completion is written on a new line under the new
#: number and the original 「[~]」 line stays. Two of those were live on
#: 2026-09-12 (C-1694, C-1699) and neither invariant above sees them: the
#: number is unique and the item is unfinished, which is exactly what a real
#: claim looks like.
#:
#: What gives it away is that the metric the claim says it will 新設 has
#: already been 新設 somewhere finished. Naming a metric as context must not
#: count - C-1726 cites its predecessor in prose - so the word has to follow
#: the name immediately.
#: Emphasis sits between the name and the word on real completion lines
#: - 「`creation_one_thumb_play` **新設 unmeasurable→9**」 - so the gap
#: allows asterisks as well as spaces. Only those: anything else between
#: them means the name was mentioned, not promised.
DECLARES_NEW = re.compile(r"`([^`]+)`[\s*]*(?:を)?[\s*]*新設")

#: Measured over 158 board versions (2026-09-11 06:00 - 2026-09-12 16:00):
#: that rule alone fires on four LIVE claims too (C-1660, C-1696, C-1701,
#: C-1704), each in exactly one version - the gap between writing a
#: completion line and flipping one's own 「[~]」. Those states are in pushed
#: versions, so the rule alone would have blocked every loop four times in
#: two days, on somebody else's half-finished edit.
#:
#: Nothing structural separates the two: claim-to-completion distance is
#: 1-8 lines for the strandings and 1-3 for the in-flight ones. What
#: separates them is that a stranding *persists* - 64 and 73 versions
#: against one. So the previous board is an input, and a claim has to be
#: stranded in both. Re-measured over the same 158 versions: the strandings
#: still fire and the four live claims fire zero times.
#:
#: The board already had a phrase for "this one is known" - 進捗監視 wrote
#: 「この行は取り残しです」 on both when it annotated them - so that is the
#: acknowledgement, and no one's text had to be edited to adopt it.
ACKNOWLEDGED = re.compile(r"この行[はも]取り残しです")


def _stranded_claims(text: str) -> dict[str, tuple[int, str]]:
    """Claims whose promised metric is already 新設 on a finished line."""

    done: set[str] = set()
    for line in text.split("\n"):
        head = HEADING.match(line)
        if head and head.group(1) in FINISHED:
            done.update(m.group(1) for m in DECLARES_NEW.finditer(line))

    out: dict[str, tuple[int, str]] = {}
    for item in read_items(text):
        if item["box"] != "~":
            continue
        promised = [m.group(1) for m in DECLARES_NEW.finditer(item["text"])]
        hit = [name for name in promised if name in done]
        if not hit:
            continue
        key = item["id"] or f"L{item['line']}"
        out[key] = (item["line"], hit[0])
    return out


def _stranded_unacknowledged(text: str, previous: str) -> list[str]:
    """Strandings that are in both boards and that nobody has noted."""

    now = _stranded_claims(text)
    before = _stranded_claims(previous)
    items = {item["id"] or f"L{item['line']}": item for item in read_items(text)}
    problems: list[str] = []
    for key, (line_number, metric) in sorted(now.items()):
        if key not in before:
            # One version only: a completion written just before its own
            # claim was flipped. That is somebody mid-edit, not a stranding.
            continue
        item = items.get(key)
        body = "\n".join(line for _, line in item["body"]) if item else ""
        if ACKNOWLEDGED.search(body):
            continue
        problems.append(
            f"L{line_number}: {key} is still 「~」 but `{metric}` is already "
            "新設 on a finished line, in this board and the one before it - "
            "a claim left behind by a renumbering. Fold the line, or note it "
            "with 「この行は取り残しです」 if it is being kept on purpose"
        )
    return problems


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


def _stamp_key(match: "re.Match[str]") -> tuple[str, str, str]:
    """Date, time and author - never the raw text.

    The heading writes 「2026-09-06 22:34 UTC ループA」 and the record under
    it writes 「2026-09-06 22:34 ループA」; some older headings drop the UTC
    on both sides. Comparing the matched strings made the check miss its
    own live example, which is how this was found.
    """

    return (match.group(1), match.group(2), match.group(3))


def _flat(lines: list[str]) -> str:
    """The item as one block of text, so a wrapped label still reads."""

    return "\n".join(line.strip() for line in lines)


def _record_blocks(item: dict) -> list[tuple[int, list[str]]]:
    """Each appended record under an item, as (line number, its lines)."""

    blocks: list[tuple[int, list[str]]] = []
    current: tuple[int, list[str]] | None = None
    for line_number, line in item["body"]:
        if RECORD.match(line):
            if current:
                blocks.append(current)
            current = (line_number, [line])
        elif current:
            current[1].append(line)
    if current:
        blocks.append(current)
    return blocks


def _misplaced_records(items: list[dict]) -> list[str]:
    """Records that landed on a neighbour rather than on their own item.

    The second invariant only sees a record that lands on an UNFINISHED
    item, and the board's finished items only ever grow - so half of the
    places a record can fall were blind. C-1450's record landed on a
    finished 「[記録]」 item at 22:09 and the check stayed green; two more
    of the same shape were on the board when this was written.

    What identifies a stray record is that TWO independent things agree
    with a different item: the stamp it carries (date, time and author -
    written by the same hand in the same commit as that item's completion
    line) and a metric name it quotes (that item's 「→ 動かす数字:」). One
    alone is not enough and misfires on the real board: records discuss
    their neighbours' metrics all the time (C-1436's names
    ``creation_puzzle_economy`` only to say it was left intact), and two
    items can share an hour. Both together have never agreed by accident.
    """

    home_of: dict[tuple[str, str], int] = {}
    metric_of: dict[int, set[str]] = {}
    for item in items:
        whole = _flat([item["text"]] + [line for _, line in item["body"]])
        metrics = set(MOVES.findall(whole))
        metric_of[item["line"]] = metrics
        stamp = STAMP.search(item["text"])
        if stamp and metrics:
            for metric in metrics:
                home_of[(_stamp_key(stamp), metric)] = item["line"]

    problems: list[str] = []
    for item in items:
        for line_number, lines in _record_blocks(item):
            stamp = STAMP.search(lines[0])
            if stamp is None:
                continue
            key = _stamp_key(stamp)
            quoted = {name for name in QUOTED.findall(_flat(lines))}
            # No shortcut for "it names its own item's metric": measured on
            # the 22:09 board, the stray record named the holder's metric in
            # passing and that escape hid the very case this exists for. The
            # two agreements below decide on their own - a record sitting on
            # its own item resolves to that item and is silent.
            for name in sorted(quoted):
                home = home_of.get((key, name))
                if home is not None and home != item["line"]:
                    problems.append(
                        f"L{line_number}: this 記録/結果 carries "
                        f"{' '.join(key)!r} and quotes `{name}`, which is the "
                        f"item at L{home} - it belongs there, not under the "
                        f"item at L{item['line']}"
                    )
                    break
    return problems


def check(text: str, previous: str | None = None) -> list[str]:
    """The invariants, in the order the repairs found them.

    ``previous`` is the last committed board. Without it the stranded-claim
    invariant is skipped, so every existing caller keeps its behaviour.
    """
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

    problems.extend(_misplaced_records(items))

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

    if previous is not None:
        problems.extend(_stranded_unacknowledged(text, previous))

    return problems


def _previous_board(board: Path) -> str | None:
    """The board as of the previous commit that changed it.

    Walks the file's own history rather than HEAD/HEAD~1: most commits do
    not touch the board, and taking the parent commit blindly returned the
    same text and skipped the check. If the working tree already differs
    from the newest recorded version, that version is the previous one;
    otherwise it is the one before it.

    Fails soft on purpose - a shallow clone, a fresh repository or a board
    outside git leaves the third invariant unchecked rather than turning a
    missing input into a refusal.
    """

    import subprocess

    listed = subprocess.run(
        ["git", "log", "--format=%H", "-3", "--", board.name],
        cwd=board.parent, capture_output=True, text=True,
    )
    if listed.returncode != 0:
        return None
    revisions = [line for line in listed.stdout.split("\n") if line.strip()]
    here = board.read_text(encoding="utf-8")
    for revision in revisions:
        shown = subprocess.run(
            ["git", "show", f"{revision}:./{board.name}"],
            cwd=board.parent, capture_output=True, text=True,
        )
        if shown.returncode == 0 and shown.stdout != here:
            return shown.stdout
    return None


def _claim_commit_times(board: Path, lines: list[int]) -> dict[int, int | None]:
    """Committer time (epoch seconds) of the commit each line came in on.

    Read from git, never from the timestamp written on the line. C-1813
    censused the board's own stamps: 73 of 687 lead their own commit by more
    than 30 minutes, median +83 and worst +719. A watch that reads the line to
    decide how long a claim has been sitting is reading the one number the
    claimer chose, which is why the stall watch already gave up on it.

    ``None`` for a line git cannot place - not yet committed, or no git at
    all. The caller prints that as unknown rather than guessing zero: an
    unknown age must not read as a fresh claim.
    """

    import subprocess

    out: dict[int, int | None] = {}
    for line in lines:
        blamed = subprocess.run(
            ["git", "blame", "--line-porcelain", "-L", f"{line},{line}", "--", board.name],
            cwd=board.parent, capture_output=True, text=True,
        )
        when: int | None = None
        if blamed.returncode == 0:
            rows = blamed.stdout.split("\n")
            # A line that is written but not committed is blamed on the
            # all-zero sha, and git stamps that pseudo-commit with *now*. Taken
            # at face value it reads 「確保から 0 分」 forever: a claim written
            # three hours ago and never pushed would stay permanently fresh and
            # never come up for the 30-minute takeover. Unknown is the honest
            # answer, so the zero sha is read before the time.
            committed = not (rows and rows[0].split(" ")[0].strip("0") == "")
            if committed:
                for row in rows:
                    if row.startswith("committer-time "):
                        try:
                            when = int(row.split()[1])
                        except (IndexError, ValueError):
                            when = None
                        break
        out[line] = when
    return out


def _age(seconds: int | None) -> str:
    if seconds is None:
        return "経過不明（commit 未確定）"
    minutes = seconds // 60
    if minutes < 60:
        return f"確保から {minutes} 分"
    return f"確保から {minutes // 60} 時間 {minutes % 60} 分"


def claims_report(text: str, board: Path, now: int | None = None) -> list[str]:
    """What the check already knows about 「~」, said out loud.

    Nothing here is new knowledge. ``_stranded_claims`` has been able to name
    the leftover claims since C-1728, and ``ACKNOWLEDGED`` has been able to say
    which of them somebody has already explained. The output printed one line -
    the item count - so every loop re-derived the same answer from prose
    instead: 22 lines of ``docs/LOOP_LOG.md`` mention C-1694 or C-1699, 19 of
    them inside a no-op explanation, over about 59 hours.

    Three rules decide what a reader may trust here (C-1819 A/B/C):

    * every 「~」 on the board appears, live or not - a claim must not be able
      to leave this list by being judged, only by being folded;
    * **a claim with no written reason is live**, however old it is. Leftover
      status is the written 「この行は取り残しです」, never the age (C-1728);
      a structurally-stranded claim nobody has explained stays on the live
      side, where ``_stranded_unacknowledged`` is already complaining about it;
    * a claim judged a leftover is still printed, named as such. Dropping it
      would let "solved by becoming invisible" score the same as solved.
    """

    import time

    claims = [item for item in read_items(text) if item["box"] == "~"]
    if not claims:
        return ["生きている確保 0 件・取り残し 0 件（「~」は 1 件も無い）"]

    stranded = _stranded_claims(text)

    # Classify first, blame second. A leftover prints no age, and asking git
    # for one is what made this slow: blaming the two real leftovers cost 3.5
    # and 3.8 seconds against 0.04 for a claim made this hour, because they are
    # two days old and blame walks that much more history. This check runs on
    # every push, so the lines whose age is never printed are never looked up -
    # 7.7s to 0.15s, and nothing in the output changes.
    live_items: list[tuple[dict, str, bool]] = []
    left: list[str] = []
    for item in claims:
        key = item["id"] or f"L{item['line']}"
        body = "\n".join(line for _, line in item["body"])
        # Written reason, not age. Both must hold to call it a leftover.
        explained = bool(ACKNOWLEDGED.search(body))
        if key in stranded and explained:
            left.append(f"    L{item['line']} {key}: 取り残し（`{stranded[key][1]}` は完了行で新設済み・理由が書かれている）")
        else:
            live_items.append((item, key, key in stranded))

    times = _claim_commit_times(board, [item["line"] for item, _, _ in live_items])
    when = int(time.time()) if now is None else now

    live: list[str] = []
    for item, key, unexplained in live_items:
        made = times.get(item["line"])
        age = _age(None if made is None else when - made)
        note = "・**理由が書かれていないので生きている扱い**" if unexplained else ""
        live.append(f"    L{item['line']} {key}: {age}{note}")

    report = [f"確保「~」{len(claims)} 件: 生きている {len(live)} 件・取り残し {len(left)} 件"]
    if live:
        report.append("  生きている:")
        report.extend(live)
    if left:
        report.append("  取り残し（作業ではない。行は持ち主が畳む）:")
        report.extend(left)
    return report


def main(argv: list[str]) -> int:
    board = Path(argv[1]) if len(argv) > 1 else BOARD
    text = board.read_text(encoding="utf-8")
    problems = check(text, _previous_board(board))
    items = read_items(text)
    numbered = sum(1 for item in items if item["id"])
    # The claim report prints either way: it is what the board says, not a
    # verdict on it, and a reader chasing an inconsistency wants it most.
    claims = claims_report(text, board)
    if problems:
        print(f"{board}: {len(problems)} 件の不整合")
        for problem in problems:
            print(f"  - {problem}")
        for line in claims:
            print(line)
        return 1
    print(f"{board}: {len(items)} 項目（うち採番 {numbered}）・不整合なし")
    for line in claims:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
