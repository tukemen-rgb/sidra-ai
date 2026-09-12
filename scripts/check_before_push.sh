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
