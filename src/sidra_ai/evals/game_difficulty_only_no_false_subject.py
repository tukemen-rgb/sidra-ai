"""A difficulty-only game request names no subject the page fails to draw.

C-1235: 「むずかしいゲームを作って」 set the difficulty to hard correctly, then
turned the *same word* into a subject: the page was titled 「むずかしい」 and the
summary said 「『むずかしい』の題材を描く型はまだ無い（題は「むずかしい」の
まま）」. A word already consumed as the difficulty cannot also be an undrawn
subject - the request named no subject at all, exactly like the bare
「ゲームを作って」. _title_from now falls back to the template's own title when
nothing but a difficulty modifier is left, so no false caveat is raised and
the title is the default. A real subject (「猫」) and a named genre are
untouched.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass


@dataclass(frozen=True)
class DifficultyOnlyResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _summary(request: str) -> str:
    from sidra_ai.creation.game_job import build_game_generator
    from sidra_ai.creation.intent import detect_creation_intent

    with tempfile.TemporaryDirectory() as tmp:
        return build_game_generator(tmp)(request, detect_creation_intent(request)).summary


def _title(request: str) -> str:
    from sidra_ai.creation.games import generate_game

    return generate_game(request).title


def evaluate_game_difficulty_only_no_false_subject() -> DifficultyOnlyResult:
    checks = 0
    failures: list[str] = []

    # Difficulty-only requests: the difficulty word must not become a subject
    # caveat or the page title, and the difficulty itself must still be right.
    cases = (
        ("むずかしいゲームを作って", "むずかしい", "hard"),
        ("簡単なゲームを作って", "簡単", "easy"),
        ("初心者向けのゲームを作って", "初心者", "easy"),
    )
    for request, word, difficulty in cases:
        summary = _summary(request)
        # No 「『…』の題材を描く型はまだ無い」 caveat naming the difficulty word.
        if "題材を描く型はまだ無い" not in summary and f"「{word}" not in summary:
            checks += 1
        else:
            failures.append(f"{request}: still treats 「{word}」 as an undrawn subject")
        # The difficulty was still read correctly.
        if f"難易度 {difficulty}" in summary:
            checks += 1
        else:
            failures.append(f"{request}: difficulty not {difficulty}")
        # The page is titled with the template default, not the difficulty word.
        if _title(request) != word and word not in _title(request):
            checks += 1
        else:
            failures.append(f"{request}: page titled 「{word}」")

    # Regression 1: a real subject still gets its caveat (fix is not a blanket
    # suppression).
    cat = _summary("猫のゲームを作って")
    if "猫" in cat and "題材を描く型はまだ無い" in cat:
        checks += 1
    else:
        failures.append("猫のゲーム lost its subject caveat")

    # Regression 2: difficulty + subject keeps the subject caveat and the
    # difficulty - only the difficulty word is discounted as a subject.
    both = _summary("むずかしい猫のゲームを作って")
    if "猫" in both and "難易度 hard" in both:
        checks += 1
    else:
        failures.append("むずかしい猫のゲーム lost its subject or its difficulty")

    # Regression 3: the bare request is still clean.
    bare = _summary("ゲームを作って")
    if "題材を描く型はまだ無い" not in bare and "タイミング釣り" in bare:
        checks += 1
    else:
        failures.append("bare ゲームを作って regressed")

    return DifficultyOnlyResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=12,
        failures=tuple(failures),
    )
