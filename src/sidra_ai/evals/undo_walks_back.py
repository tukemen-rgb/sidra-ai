"""Does 「元に戻して」 walk back through the history, or bounce off it?

C-1816. An undo writes a NEW version holding an OLD state, and it landed at
the end of the chain like any other write, so the next undo read its
predecessor as "the state I was just in" and copied that back. Driven on
2026-09-14: create → 難しくして → 差し色を青にして → 元に戻して ×3 ran the accent
off, on, off, for ever. ``difficulty`` stayed ``hard`` permanently and the
first change could not be reached, while every reply said 「一つ前の版に戻し
ました」 - true of the files, quietly false about the history.

It stayed invisible because the undo summary named only difficulty, theme and
title: an undo that moved just the accent reported nothing at all, so three
rounds of oscillation read as the same answer repeating.

``restored_from`` gives each undo a pointer to what it copied, so a run of
undos can be followed back to where it entered the chain. Nothing is deleted -
every version stays on disk, which §23 requires and which the summary promises
in 「旧版のファイルもそのまま残っています」 - only which version counts as
"previous" changed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sidra_ai.evals.scratch import scratch_dir


@dataclass(frozen=True)
class UndoWalksBackResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service(tag: str):
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    root = Path(scratch_dir(prefix=f"undo-{tag}-")) / "s"
    return SidraService(Settings(data_dir=str(root))), root


def _newest(root: Path) -> dict:
    metas = sorted(root.rglob("game-*.meta.json"), key=lambda p: (p.stat().st_mtime, p.name))
    return json.loads(metas[-1].read_text(encoding="utf-8")) if metas else {}


def _count(root: Path) -> int:
    return len(list(root.rglob("game-*.html")))


def evaluate_undo_walks_back() -> UndoWalksBackResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) two changes, then undo twice, reaches the first state --------
    svc, root = _service("walk")
    svc.chat("レースゲームを作って")
    svc.chat("さっきのゲームを難しくして")
    svc.chat("さっきのゲームの差し色を青にして")
    before_files = _count(root)

    first = svc.chat("元に戻して").get("answer") or ""
    state = _newest(root)
    add((state.get("panel") or {}).get("accent") in (None, ""),
        "A: the first undo did not take the accent back")
    add("差し息" not in first and "差し色" in first,
        f"A: the first undo did not name what it undid: {first[:60]}")

    second = svc.chat("元に戻して").get("answer") or ""
    state = _newest(root)
    add(state.get("difficulty") == "normal",
        f"A: the second undo did not reach the first change (difficulty={state.get('difficulty')})")
    add("hard→normal" in second, f"A: the second undo did not name the difficulty: {second[:60]}")

    # --- (B) ...and then it says so, in the sentence that is true ---------
    third = svc.chat("元に戻して").get("answer") or ""
    add("これ以上戻せる版がありません" in third,
        f"B: walking off the start did not say so: {third[:60]}")
    add("まだ一度も修正していない" not in third,
        "B: a reader who revised twice was told they never revised")

    # --- (C) nothing on disk is lost (§23) --------------------------------
    add(_count(root) >= before_files + 2,
        "C: an undo removed a version instead of writing a new one")

    # --- (D) a page nobody revised still gets ITS sentence ----------------
    # Two ways to have nothing to go back to; they are not the same message.
    svc2, _ = _service("fresh")
    svc2.chat("パズルゲームを作って")
    fresh = svc2.chat("元に戻して").get("answer") or ""
    add("まだ一度も修正していない" in fresh,
        f"D: an unrevised page lost its own sentence: {fresh[:60]}")

    # --- (E) an ordinary revision is untouched ----------------------------
    svc3, root3 = _service("plain")
    svc3.chat("パズルゲームを作って")
    done = svc3.chat("さっきのゲームを難しくして").get("answer") or ""
    add("normal→hard" in done, f"E: an ordinary revision regressed: {done[:60]}")
    add(_newest(root3).get("restored_from", "") == "",
        "E: an ordinary revision was marked as a restore")

    return UndoWalksBackResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = ["UndoWalksBackResult", "evaluate_undo_walks_back"]
