"""Does the project summary admit a genre fall-back the game path admits?

C-1285: the standalone game path says 「代わりに既定の…型で作りました」 when a genre
it has no template for lands on the default fishing page (game_job). The project
bundles that same game.html but its summary listed the files and said nothing, so
「アクションゲームの制作一式を作って」 read as a delivered action game. The summary
now carries the same admission - for a recognised-but-unsupported genre and for a
request that named no genre whose subject the default does not draw - and stays
silent for a genre the tool actually builds.

Checks drive the router's project generator and read the summary it returns.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass

_FALLBACK = "代わりに既定の"
_DEFAULT = "タイミング釣り"


@dataclass(frozen=True)
class ProjectGenreFallbackResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _summary(request: str) -> str:
    from sidra_ai.creation.intent import detect_creation_intent
    from sidra_ai.creation.router import build_default_router

    tmp = tempfile.mkdtemp(prefix="proj-genre-")
    router = build_default_router(data_dir=tmp)
    out = router.route(request, detect_creation_intent(request), [])
    return out.summary


def evaluate_project_summary_discloses_genre_fallback() -> ProjectGenreFallbackResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # 1: an unrecognised genre (no template) admits the fall-back and names the
    #    default template and the subject.
    action = _summary("アクションゲームの制作一式を作って")
    add(_FALLBACK in action, "unrecognised-genre project hides the fall-back")
    add(_DEFAULT in action, "unrecognised-genre project omits the default template")
    add("アクションゲーム" in action, "unrecognised-genre project drops the subject")

    # 2: a recognised-but-unsupported genre names the genre it could not build.
    fighter = _summary("格闘ゲームの制作一式を作って")
    add(_FALLBACK in fighter and "対戦格闘" in fighter,
        "unsupported-genre project hides the substitution")

    # 3: a genre the tool builds draws no caveat - a caveat on a request we did
    #    satisfy is its own dishonesty.
    fishing = _summary("釣りゲームの制作一式を作って")
    add(_FALLBACK not in fishing, "a built genre (釣り) wrongly drew a fall-back caveat")
    shooter = _summary("シューティングの制作一式を作って")
    add(_FALLBACK not in shooter, "a built genre (シューティング) wrongly drew a caveat")

    # 4: the admission carries no fabricated figure.
    if _FALLBACK in action:
        note = action.split("。")
        caveat = next((s for s in note if _FALLBACK in s), "")
        add(not any(ch.isdigit() for ch in caveat), f"caveat carries a digit: {caveat!r}")
    else:
        failures.append("no caveat to check for a digit")

    # 5: the project is still whole - the files are still listed and written.
    add("game.html" in action and "scenario.md" in action,
        "the project stopped listing its files")

    total = 8
    return ProjectGenreFallbackResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ProjectGenreFallbackResult",
    "evaluate_project_summary_discloses_genre_fallback",
]
