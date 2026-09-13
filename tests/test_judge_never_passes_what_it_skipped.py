"""測れなかったものを合格にしない (C-1791, C-1755 の続き).

C-1755's defect: a bundled worker that cannot measure a template returns no
gaps, and the caller reads no gaps as a pass::

    for key, said in zip(keys, in_parallel(...)):
        if said:   gaps.extend(said)
        else:      ok.append(key)      # <- "skipped" lands here

Two metrics then described ten templates as driven when seven were, and
because no value moved, ``--compare`` said nothing.

``test_no_bundled_worker_appends_to_a_list_it_does_not_own`` forbids one
*mechanism* - reaching out to a list you do not own. It does not forbid the
*shape*: returning your own gaps list without having put anything in it.
This file forbids the shape.

What separates a sound early return from the bug is whether anything has
been recorded yet. ``if _ink_bad: return gaps`` is fine because the loop
above appended; ``if key not in table: return gaps`` is the bug because
nothing has. So the rule is positional: an append to that list must appear
earlier in the function than the return.

The first draft of this rule asked whether the return's own *branch*
appended, which excused every ``if ...: return gaps`` guard - including the
one it exists to catch. The destruction run caught it: the sabotage scored
full marks. Recorded here because the near-miss is the point.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "product_metrics.py"


def _fills(fn: ast.FunctionDef, name: str, before_line: int) -> bool:
    for n in ast.walk(fn):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in ("append", "extend")
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == name
            and n.lineno < before_line
        ):
            return True
    return False


def _offenders(source: str) -> list[str]:
    tree = ast.parse(source)
    bad: list[str] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef) or not fn.name.endswith("_one"):
            continue
        lists = {
            t.id
            for st in ast.walk(fn)
            if isinstance(st, (ast.Assign, ast.AnnAssign))
            for t in (st.targets if isinstance(st, ast.Assign) else [st.target])
            if isinstance(t, ast.Name) and "gap" in t.id.lower()
        }
        if not lists:
            continue
        for node in ast.walk(fn):
            for field in ("body", "orelse", "finalbody"):
                block = getattr(node, field, None)
                if not isinstance(block, list):
                    continue
                for st in block:
                    if (
                        isinstance(st, ast.Return)
                        and isinstance(st.value, ast.Name)
                        and st.value.id in lists
                        and not _fills(fn, st.value.id, st.lineno)
                    ):
                        bad.append(f"{fn.name}:L{st.lineno}")
    return bad


def test_no_worker_returns_a_gap_list_it_never_filled() -> None:
    assert _offenders(SOURCE.read_text(encoding="utf-8")) == []


def test_the_rule_catches_the_shape_c1755_found() -> None:
    """The sabotage this file is about, run against the rule itself.

    Without this the rule could quietly stop matching - which is exactly
    what its first draft did.
    """

    sample = (
        "def _demo_one(key):\n"
        "    gaps: list[str] = []\n"
        "    if key not in TABLE:\n"
        "        return gaps\n"
        "    gaps.append('measured')\n"
        "    return gaps\n"
    )

    assert _offenders(sample) == ["_demo_one:L4"]


def test_the_rule_does_not_cry_wolf_on_a_sound_early_return() -> None:
    """A guard that returns *after* recording is how every honest probe
    stops early. Flagging those would make the rule useless."""

    sample = (
        "def _demo_one(key):\n"
        "    gaps: list[str] = []\n"
        "    if broken(key):\n"
        "        gaps.append('broken')\n"
        "        return gaps\n"
        "    return gaps\n"
    )

    assert _offenders(sample) == []
