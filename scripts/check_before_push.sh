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

markers=$(grep -rn '^<<<<<<<\|^>>>>>>> ' docs/ src/ tests/ scripts/ 2>/dev/null)
if [ -n "$markers" ]; then
  echo "REFUSED: conflict markers are still in the tree"
  echo "$markers" | head -20
  fail=1
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
