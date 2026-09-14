"""Does a revision that changes nothing keep its hands off the history?

C-1817, next door to C-1816. Asking 「難しくして」 at maximum difficulty already
refused to claim a change - it answers 「変更なし（すでにその設定です）」 - but it
wrote a version anyway, because the file was written BEFORE the comparison
that discovers there is nothing to record. Two such asks left two versions
holding identical pages, and 「元に戻して」 then had to step through them, saying
「一つ前の版に戻しました」 each time while nothing moved. That is exactly the
symptom C-1816 fixed, reached by another door.

Undo is excluded on purpose: it always restores something.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.evals.scratch import scratch_dir


@dataclass(frozen=True)
class NoChangeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service():
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    root = Path(scratch_dir(prefix="no-change-")) / "s"
    return SidraService(Settings(data_dir=str(root))), root


def evaluate_no_change_writes_no_version() -> NoChangeResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    svc, root = _service()
    count = lambda: len(list(root.rglob("game-*.html")))

    svc.chat("レースゲームを作って")
    after_build = count()

    # --- (A) a real revision writes one -----------------------------------
    real = svc.chat("さっきのゲームを難しくして").get("answer") or ""
    add(count() == after_build + 1, "A: a real revision did not write a version")
    add("normal→hard" in real, f"A: a real revision stopped reporting: {real[:50]}")
    after_real = count()

    # --- (B) ...and one that changes nothing does not ----------------------
    for _ in range(2):
        said = svc.chat("さっきのゲームを難しくして").get("answer") or ""
        add("変更なし" in said, f"B: a no-op stopped saying so: {said[:50]}")
        add("新しい版は作っていません" in said,
            f"B: a no-op did not say it wrote nothing: {said[:60]}")
    add(count() == after_real, f"B: no-ops wrote {count() - after_real} version(s)")

    # --- (C) so undo reaches the real change in one step ------------------
    undone = svc.chat("元に戻して").get("answer") or ""
    add("hard→normal" in undone, f"C: undo did not reach the real change: {undone[:60]}")

    # --- (D) undo still writes its own version (C-1816 unbroken) ----------
    add(count() == after_real + 1, "D: undo stopped writing a version")

    # --- (E) nothing on disk was removed (§23) ----------------------------
    add(count() >= after_build, "E: a version disappeared from disk")

    return NoChangeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = ["NoChangeResult", "evaluate_no_change_writes_no_version"]
