"""Does game.html disclose that a requested genre was substituted?

C-1788. When a request names a genre SIDRA cannot build (「格闘ゲーム」) or a
subject with no matching template (「猫のゲーム」), ``generate_game`` builds the
default template and, for a decline, swaps the title - but the page subtitle said
only 「難易度 X / ジャンル 釣り」, with no word that a different genre was asked
for. The chat summary disclosed the substitution; game.html - the artifact that is
reopened and forwarded - stayed silent. ``genre_fallback_note`` (already the
page-shaped wording used by the project flow) is now shown on the single-game
page too. A satisfied request adds no note.

The checks read the real ``generate_game`` HTML and the ``game_job`` summary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.game_job import build_game_generator
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.scratch import scratch_dir

_NOTE = "代わりに既定"


@dataclass(frozen=True)
class GameFallbackPageResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_game_page_discloses_genre_fallback() -> GameFallbackPageResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    declined = generate_game("格闘ゲームを作って").html      # genre we cannot build
    subject = generate_game("猫のゲームを作って").html        # subject with no template
    supported = generate_game("パズルゲームを作って").html    # a genre we build

    # --- (A) a declined genre is disclosed on the page ------------------
    add(_NOTE in declined,
        "A: the page does not disclose the genre substitution for 「格闘」")
    # --- (B) a subject with no template is disclosed too ----------------
    add(_NOTE in subject,
        "B: the page does not disclose the default-template fallback for 「猫」")
    # --- (C) a genre we build carries no such note (no false positive) --
    add(_NOTE not in supported,
        "C: a buildable genre wrongly claims a substitution")
    # --- (D) the substituted page is still a playable game --------------
    add("<canvas" in declined and "<script" in declined,
        "D: the substituted page is no longer a playable game")
    # --- (E) the chat summary still discloses the substitution ----------
    gen = build_game_generator(scratch_dir())
    outcome = gen("格闘ゲームを作って", detect_creation_intent("格闘ゲームを作って"))
    summary = getattr(outcome, "summary", "") or ""
    add("代わりに既定" in summary or "まだ作れない" in summary,
        "E: the chat summary lost its substitution disclosure")
    # --- (F) a buildable genre's subtitle still names the built genre ---
    tags = re.findall(r'<p class="tag">([^<]*)</p>', supported)
    add(any("ジャンル パズル" in t for t in tags),
        f"F: the buildable-genre subtitle does not name the genre: {tags[:2]}")

    total = 6
    return GameFallbackPageResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "GameFallbackPageResult",
    "evaluate_game_page_discloses_genre_fallback",
]
