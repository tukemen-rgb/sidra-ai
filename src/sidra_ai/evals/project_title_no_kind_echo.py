"""Does a project title drop the kind word, or echo it into a doubled summary?

C-1274-adjacent: documents (C-1246), decks (C-1249), art/GIF (C-1265) and 3D all
strip the kind noun from the title, but the project bundle did not.
「シューティングゲームの制作一式を作って」 came back
「『シューティングゲームの制作一式』の制作一式を…作りました」 - 制作一式 twice - and
「忍者ゲームのプロジェクト一式を作って」 the same. The title should be the subject
alone (「シューティングゲーム」, 「忍者ゲーム」), like every other generator.

Measured through the real chat path: a named-subject request shows the subject
alone and never the doubled form; a bare kind word still produces a handled
bundle with a fallback title.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: (request, subject, doubled-form-that-must-not-appear)
_NAMED: tuple[tuple[str, str, str], ...] = (
    ("シューティングゲームの制作一式を作って", "シューティングゲーム", "シューティングゲームの制作一式"),
    ("忍者ゲームのプロジェクト一式を作って", "忍者ゲーム", "忍者ゲームのプロジェクト一式"),
    ("レースゲーム制作一式を作って", "レースゲーム", "レースゲーム制作一式"),
)


@dataclass(frozen=True)
class ProjectTitleResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    return SidraService(Settings(data_dir=str(Path(tempfile.mkdtemp(prefix="proj-title-")) / "s")))


def evaluate_project_title_no_kind_echo() -> ProjectTitleResult:
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

    for request, subject, doubled in _NAMED:
        a = answer(request)
        # The subject stands alone in the title, and the kind word is not echoed
        # into it (no 「<subject>の制作一式」 quoted before the 制作一式 phrase).
        add(f"「{subject}」" in a and f"「{doubled}」" not in a,
            f"{request!r}: title echoes the kind word: 「{a[:70]}」")

    # A bare kind word still produces a handled bundle with a fallback title.
    bare = service.chat("プロジェクト一式を作って") or {}
    handled = ((bare.get("creation") or {}).get("outcome") or {}).get("handled")
    add(bool(handled) and "作りました" in str(bare.get("answer") or ""),
        "a bare 「プロジェクト一式を作って」 was not handled")

    total = len(_NAMED) + 1
    return ProjectTitleResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["ProjectTitleResult", "evaluate_project_title_no_kind_echo"]
