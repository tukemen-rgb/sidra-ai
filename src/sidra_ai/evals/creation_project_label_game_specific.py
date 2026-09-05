"""Does the unbuildable decline call the project kind by what it really makes?

C-1263: C-1261's honest decline lists the buildable kinds, and the project kind
was labelled 「企画一式」. But PROJECT makes a *game* production bundle
(scenario.md, structure.md, features.md, assets/, game.html, production-log.md),
not a generic plan - so 「新規事業の企画を作って」 was declined while the same
message offered 「企画一式」, contradicting itself and inviting a retry that would
either decline again or build a game bundle for a business plan. The label is
now 「ゲーム制作一式」, which says what it is.

Measured through the real chat path: the decline names the project kind as game
production and never offers a bare 「企画一式」, a business 企画 request is declined
with that clear label, and a genuine 「企画から作って」 still builds a project.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_GAME_PROJECT_LABEL = "ゲーム制作一式"
_MISLEADING_LABEL = "企画一式"  # bare form; must not stand alone in a decline


@dataclass(frozen=True)
class ProjectLabelResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    return SidraService(Settings(data_dir=str(Path(tempfile.mkdtemp(prefix="proj-label-")) / "s")))


def _bare_misleading(answer: str) -> bool:
    """True if 「企画一式」 appears other than inside 「ゲーム制作一式」."""

    return _MISLEADING_LABEL in answer.replace(_GAME_PROJECT_LABEL, "")


def evaluate_creation_project_label_game_specific() -> ProjectLabelResult:
    service = _service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    def answer(text: str) -> str:
        return str((service.chat(text) or {}).get("answer") or "")

    # An ordinary unbuildable request lists the kinds - project named as game.
    excel = answer("Excelを作って")
    add(_GAME_PROJECT_LABEL in excel, f"decline does not name project as game production: 「{excel[:80]}」")
    add(not _bare_misleading(excel), "decline still offers a bare 「企画一式」")

    # A business 企画 request: declined, and named as game production so it does
    # not read as an offer to make the plan.
    plan = answer("新規事業の企画を作って")
    add("作れません" in plan, f"a business 企画 request was not declined: 「{plan[:60]}」")
    add(_GAME_PROJECT_LABEL in plan and not _bare_misleading(plan),
        f"business 企画 decline still offers a bare 「企画一式」: 「{plan[:90]}」")

    # Control: a genuine project request still builds, not declined.
    built = answer("企画から作って")
    add("制作一式" in built and "作れません" not in built,
        f"a real project request no longer builds: 「{built[:60]}」")

    return ProjectLabelResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=5,
        failures=tuple(failures),
    )


__all__ = ["ProjectLabelResult", "evaluate_creation_project_label_game_specific"]
