#!/usr/bin/env python3
"""No judge reaches past the shared scratch helper (C-1770), checked before a push.

C-1770 moved ninety-odd call sites onto ``evals/scratch.py`` and fixed the
invariant with an AST test, because a judge that makes its own temporary
directory and never removes it is what filled this container's disk - and a
full disk makes the collector die partway, after which ``--compare`` reports
every metric it never reached as REGRESSED and LOST. That happened, and was
read as a product failure before the real cause was found. The apparatus was
corrupting its own measurements.

The test works. What it cannot do is arrive in time. Measured 2026-09-13, the
day C-1770 landed: of the four judges added after it that needed scratch
space, **three reached for ``tempfile.mkdtemp`` directly** - the fourth was
the only one that used the helper. Each was caught, but only by the full
suite, which takes about forty minutes, so each one sat on ``main`` red until
somebody else's cycle tripped over it. Three separate loops spent part of a
cycle on it in one evening, and two of them were not the authors.

So the same scan runs here, from ``check_before_push.sh``, in the seconds
before a push instead of the forty minutes after one. Nothing about the rule
changes: this file and the test read the tree the same way, with the AST, so a
call spelled across two lines still counts and a string that merely mentions
``mkdtemp`` does not.

Exit 0 when clean, 1 when a judge calls it directly, 2 when the scan could not
read the judges at all - because a check that reads nothing must not pass.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

#: Where the judges live, relative to the repository root.
EVALS = Path("src/sidra_ai/evals")

#: The one file allowed to call it: the shared helper itself.
HELPER = "scratch.py"


def direct_callers(evals: Path = EVALS) -> list[str]:
    """Judges that call ``*.mkdtemp(...)`` themselves, by file name."""

    found: list[str] = []
    for path in sorted(evals.glob("*.py")):
        if path.name == HELPER:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "mkdtemp"
            ):
                found.append(path.name)
                break
    return found


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    evals = root / EVALS
    if not evals.is_dir():
        print(f"REFUSED: {EVALS} is not there, so the scan read no judges")
        return 2
    names = sorted(p.name for p in evals.glob("*.py") if p.name != HELPER)
    if not names:
        print(f"REFUSED: no judges found under {EVALS}, so the scan read nothing")
        return 2

    direct = direct_callers(evals)
    if direct:
        print(
            f"REFUSED: {len(direct)} of {len(names)} judge(s) call mkdtemp "
            f"directly instead of evals/scratch.py's scratch_dir() (C-1770)"
        )
        for name in direct:
            print(f"  {EVALS}/{name}")
        print("  Fix: `from sidra_ai.evals.scratch import scratch_dir` and call it.")
        return 1
    print(f"{len(names)} judges: none reaches past scratch_dir()")
    return 0


if __name__ == "__main__":
    sys.exit(main())
