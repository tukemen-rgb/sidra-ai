"""Do the project's design docs disclose a substituted genre, not just the log?

C-1790. When a project request names a genre SIDRA cannot build (「格闘ゲームを
企画から作って」), ``scaffold_project`` derives the default template (fishing) and
writes ``scenario.md`` / ``structure.md`` / ``features.md`` titled 「格闘ゲーム —
脚本/構成/機能設定」 that describe the *fishing* mechanic under a fighting title.
Only ``production-log.md`` disclosed the swap (C-1605); the three design docs -
the ones a 社長 opens first - said nothing, so a reader of 「格闘ゲーム — 脚本」
believed game.html was a fighting game.

``genre_fallback_note`` is already the single source of truth for the chat
summary (C-1285), the game page (C-1788) and the production log (C-1605). It is
now shown in each design doc's header too. A buildable genre adds no note.

The checks drive the real ``scaffold_project`` and read the files it writes.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.projects import scaffold_project
from sidra_ai.evals.scratch import scratch_dir

_NOTE = "代わりに既定"
_DECLINED = "格闘ゲームを企画から作って"   # a genre we cannot build -> fishing
_BUILDABLE = "パズルゲームを企画から作って"  # a genre we build -> puzzle


@dataclass(frozen=True)
class ProjectDocsFallbackResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _docs(request: str) -> dict[str, str]:
    root = scaffold_project(request, scratch_dir()).root
    out: dict[str, str] = {}
    for name in ("scenario.md", "structure.md", "features.md", "production-log.md"):
        path = root / name
        out[name] = path.read_text(encoding="utf-8") if path.exists() else ""
    return out


def evaluate_project_docs_disclose_genre_fallback() -> ProjectDocsFallbackResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    declined = _docs(_DECLINED)
    buildable = _docs(_BUILDABLE)

    # --- (A) the scenario doc discloses the substitution -----------------
    add(_NOTE in declined["scenario.md"],
        "A: scenario.md does not disclose the genre substitution for 「格闘」")
    # --- (B) the structure doc discloses it too --------------------------
    add(_NOTE in declined["structure.md"],
        "B: structure.md does not disclose the genre substitution for 「格闘」")
    # --- (C) the features doc discloses it too ---------------------------
    add(_NOTE in declined["features.md"],
        "C: features.md does not disclose the genre substitution for 「格闘」")
    # --- (D) a buildable genre adds no note (no false positive) ----------
    add(_NOTE not in buildable["scenario.md"],
        "D: a buildable genre's scenario.md wrongly claims a substitution")
    # --- (E) the production log still discloses it (C-1605 preserved) -----
    add(_NOTE in declined["production-log.md"],
        "E: production-log.md lost its substitution disclosure")
    # --- (F) the note is additive: the doc is still the real spec ---------
    #     A note that had replaced the design doc would pass A-C while
    #     losing the fishing spec the docs are for; assert the mechanic and
    #     the difficulty spec still stand beside the disclosure.
    add("遊びの芯" in declined["scenario.md"]
        and "難易度パラメータ" in declined["features.md"],
        "F: the disclosure replaced the design docs instead of augmenting them")

    total = 6
    return ProjectDocsFallbackResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ProjectDocsFallbackResult",
    "evaluate_project_docs_disclose_genre_fallback",
]
