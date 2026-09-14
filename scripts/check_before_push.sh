#!/usr/bin/env bash
# The gate that belongs immediately before `git push`, not after a rebase
# (C-1660). Three slips in one session - a number already claimed, the same
# again, and a BACKLOG pushed with conflict markers still in it - all had one
# cause: a check was run, printed the problem, and the next command ran anyway.
#
# check_backlog_board.py exits 0 even when it reports an inconsistency, so its
# OUTPUT is what matters. This script turns both checks into an exit code.
set -u
cd "$(dirname "$0")/.." || exit 2
fail=0

# C-1723: this read four directories and called it "the tree". Measured
# 2026-09-12: 1976 files are tracked and only 920 of them are under
# docs/src/tests/scripts, so conflict markers in `.env.example`,
# `pyproject.toml`, `README.md`, `.github/` or `.claude/` got "OK to push".
# `.env.example` is the one that hurts - operators copy it into their own
# `.env`, so a marker lands in a live configuration.
#
# `git grep` asks git which files exist instead of naming directories, and
# `--untracked` keeps what the old `grep -r` also covered: a file not yet
# added. Ignored paths stay out (`--untracked` honours .gitignore), so
# `.venv` and `.sidra` are not scanned. The two patterns are unchanged, so
# behaviour inside the original four directories is identical.
#
# No `=======` pattern: a markdown setext underline is the same characters
# and docs/ has real ones (C-1709). That would be a false red in the gate.
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # A check that reads nothing passes for the wrong reason - which is the
  # whole of C-1723. Say so instead of printing "OK to push".
  echo "REFUSED: not inside a git work tree, so the marker scan read nothing"
  exit 2
fi

markers=$(git grep --untracked -n -e '^<<<<<<<' -e '^>>>>>>> ' 2>/dev/null)
if [ -n "$markers" ]; then
  echo "REFUSED: conflict markers are still in the tree"
  echo "$markers" | head -20
  fail=1
fi

# C-1733: a log line must not claim a time it has not reached. Measured
# 2026-09-12 over all 1818 timestamped lines: 95.3% sit within +5 minutes of
# their commit, but 86 lead by more, the worst by 11.7 hours, and reading
# order steps backwards at 129 places. Only the lines this push ADDS are
# judged - the 86 already in the file would make every loop red, which is
# the trap C-1728 walked into.
times=$(python scripts/check_log_times.py 2>&1)
if [ "$?" -ne 0 ]; then
  echo "$times"
  fail=1
fi

# C-1770's invariant, checked in the seconds before a push instead of the
# forty minutes after one. Measured 2026-09-13, the day C-1770 landed: of the
# four judges added after it that needed scratch space, three reached for
# `tempfile.mkdtemp` directly, and each sat on main red until somebody else's
# cycle tripped over the full suite. Three loops spent part of a cycle on it in
# one evening and two of them had not written the judge. The scan is the same
# AST read as the test, so the rule does not fork.
scratch=$(python scripts/check_eval_scratch.py 2>&1)
if [ "$?" -ne 0 ]; then
  echo "$scratch"
  fail=1
fi

# C-1800: and the number this push claims must not already head somebody
# else's item. The board check above sees a number that heads two items HERE,
# which is the ordinary outcome and is already refused. What it cannot see is
# the case where the other loop's claim was dropped in the rebase: no duplicate
# remains, nothing refuses, and the push deletes their item from origin/main.
# Measured 2026-09-14 in a throwaway repository - push rc=0, their claim gone.
# Passes with a note when origin/main cannot be read (check_log_times.py's
# precedent), and never says it checked when it did not (C-1723).
numbers=$(python scripts/check_numbers_upstream.py 2>&1)
rc=$?
# Printed either way, like the board check below: when origin cannot be read
# this check passes with a NOTE, and a NOTE nobody sees is the same as
# claiming it looked (C-1723). Measured - driving the gate rather than the
# script showed the note being swallowed on success.
if [ "$rc" -ne 0 ]; then
  # The whole reason, not a tail of it: a refusal has to name the number and
  # say what to do about it.
  echo "$numbers"
  fail=1
else
  # And the verdict is shown even when it passes, because when origin cannot
  # be read this check passes with a NOTE - and a NOTE nobody sees is the same
  # as claiming it looked (C-1723).
  echo "$numbers" | tail -1
fi

board=$(python scripts/check_backlog_board.py 2>&1)
echo "$board" | tail -3
if echo "$board" | grep -q '不整合なし'; then
  :
else
  echo "REFUSED: the board reports an inconsistency (the script exits 0 anyway)"
  fail=1
fi

if [ "$fail" -eq 0 ]; then echo "OK to push"; fi
exit "$fail"
