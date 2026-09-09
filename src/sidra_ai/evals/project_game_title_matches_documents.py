"""Does a project's game.html carry the same title as its documents?

C-1621. scaffold_project computes one canonical title (「制作一式」 stripped, the
same title every .md stage uses) and its own comment warns that "re-deriving per
stage is how two files end up disagreeing about the same game". But the GAME
stage passed the raw request to generate_game, which re-derived a title keeping
「制作一式」 - a project kind-word games.py does not strip. So the game.html
<title> read 「料理アプリの制作一式」 while every .md read 「料理アプリ」: one
bundle, two titles.

The GAME stage now passes title_override so the game carries the project's
canonical title. The .md stages, the templates and gameplay are unchanged.

The checks build real projects and read the game <title> against the scenario
H1 and the project's own title.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

_BUNDLE_KIND = "制作一式"
_REQUESTS = (
    "料理アプリの制作一式を作って",       # non-game subject -> fishing fallback
    "宇宙シューティングゲームの制作一式を作って",  # game word, unsupported -> fallback
    "釣りゲームの制作一式を作って",       # a real supported game
)
_TRADEMARK = "ゼルダの制作一式を作って"  # name is someone's -> renamed to default


@dataclass(frozen=True)
class ProjectGameTitleResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _build(request: str):
    from sidra_ai.creation.projects import scaffold_project

    tmp = Path(tempfile.mkdtemp(prefix="proj-title-"))
    project = scaffold_project(request, tmp)
    html = (project.root / "game.html").read_text(encoding="utf-8")
    game_title = re.search(r"<title>(.*?)</title>", html)
    scenario = (project.root / "scenario.md").read_text(encoding="utf-8")
    h1 = re.search(r"#\s*(.+?)\s*—", scenario)
    return project.title, (game_title.group(1) if game_title else ""), (h1.group(1) if h1 else "")


def evaluate_project_game_title_matches_documents() -> ProjectGameTitleResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for request in _REQUESTS:
        title, game_title, h1 = _build(request)
        add(game_title == title,
            f"{request!r}: game <title> {game_title!r} != project title {title!r}")
        add(h1 == title,
            f"{request!r}: scenario H1 {h1!r} != project title {title!r}")
        add(_BUNDLE_KIND not in game_title,
            f"{request!r}: game <title> keeps the bundle kind-word: {game_title!r}")

    # A trademarked name is renamed to the template default; the game must still
    # match the documents (and carry no bundle kind-word).
    t_title, t_game, _ = _build(_TRADEMARK)
    add(t_game == t_title and _BUNDLE_KIND not in t_game,
        f"{_TRADEMARK!r}: renamed game <title> {t_game!r} != project title {t_title!r}")

    total = 10
    return ProjectGameTitleResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ProjectGameTitleResult",
    "evaluate_project_game_title_matches_documents",
]
