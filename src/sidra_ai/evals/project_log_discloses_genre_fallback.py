"""Does the production log admit a default-template fallback, not just the chat?

C-1605. The project summary says when game.html fell back to the default
template (C-1285), but a project is a directory that is saved and forwarded, so
the record itself must say it too (as the report discloses set-aside evidence,
C-1281, and the 3D preview its default shape, C-1283). production-log.md now
carries a 「既定テンプレートへのフォールバック」 section when there was a fallback,
and nothing when a genuine game was built - no false caveat. The chat summary
is unchanged, sharing one source of truth with the log.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

_MARK = "既定テンプレートへのフォールバック"
_FALLBACK_SENTENCE = "代わりに既定の"


@dataclass(frozen=True)
class ProjectLogFallbackResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _log_for(request: str) -> str:
    from sidra_ai.creation.projects import scaffold_project

    tmp = Path(tempfile.mkdtemp(prefix="proj-fallback-"))
    scaffold_project(request, tmp)
    root = next((tmp / "artifacts" / "projects").iterdir())
    return (root / "production-log.md").read_text(encoding="utf-8")


def _summary_for(request: str) -> str:
    from sidra_ai.creation.intent import detect_creation_intent
    from sidra_ai.creation.project_job import build_project_generator

    gen = build_project_generator(tempfile.mkdtemp())
    return gen(request, detect_creation_intent(request)).summary


def evaluate_project_log_discloses_genre_fallback() -> ProjectLogFallbackResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # A fallback (non-game subject, or an unsupported genre) is disclosed in the
    # persisted log, with the same sentence the summary uses.
    for request in ("料理アプリの制作一式を作って", "アクションゲームの制作一式を作って",
                    "ブログの制作一式を作って"):
        log = _log_for(request)
        add(_MARK in log, f"{request!r}: log did not disclose the fallback")
        add(_FALLBACK_SENTENCE in log, f"{request!r}: log lacks the fallback sentence")

    # A genuine, supported game draws no caveat in the log.
    for request in ("釣りゲームの制作一式を作って", "パズルゲームの制作一式を作って"):
        log = _log_for(request)
        add(_MARK not in log, f"{request!r}: log drew a false fallback caveat")

    # The chat summary is unchanged: it still admits the fallback (C-1285) for a
    # substitution and stays quiet for a genuine game.
    add(_FALLBACK_SENTENCE in _summary_for("料理アプリの制作一式を作って"),
        "summary lost its fallback admission")
    add(_FALLBACK_SENTENCE not in _summary_for("釣りゲームの制作一式を作って"),
        "summary drew a false fallback caveat for a genuine game")

    total = 10
    return ProjectLogFallbackResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ProjectLogFallbackResult",
    "evaluate_project_log_discloses_genre_fallback",
]
