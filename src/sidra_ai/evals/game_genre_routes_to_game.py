"""Does a bare game-genre request reach the game maker, or fall to Q&A?

C-1253: 「ブロック崩しを作って」 and 「3目並べを作って」 came back
``kind=unknown`` (weak) and fell to the question path - a reader who asked for
a game got an answer about nginx config or a worklog. The intent detector knew
a request was a game only when it carried the word 「ゲーム」 or a genre already
in the vocabulary; 「ブロック崩しゲームを作って」 routed, 「ブロック崩しを作って」
did not. These are unmistakably game requests, so they belong in the game path -
which then declines honestly (「…型はまだ作れない」) exactly as テトリス does.
The same vocabulary gap C-1240 closed for クイズ/麻雀, a few common genres along.

The checks classify the bare genre spellings and a couple of controls, and
confirm each genre routes to GAME while a real question stays a question.
"""

from __future__ import annotations

from dataclasses import dataclass

#: (request, expected kind value, or "not-creation")
_CASES = (
    ("ブロック崩しを作って", "game"),
    ("3目並べを作って", "game"),
    ("三目並べを作って", "game"),
    ("クリッカーを作って", "game"),
    ("３目並べを作って", "game"),  # fullwidth digit, NFKC-folded
    # controls: a request that already worked, and real questions that must
    # stay on the question path - the fix widens the game words, not creation.
    ("ブロック崩しゲームを作って", "game"),
    ("パズルを作って", "game"),
    ("国内最大級と言えるか", "not-creation"),
    ("天気を教えて", "not-creation"),
)


@dataclass(frozen=True)
class GameGenreRoutesToGameResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_game_genre_routes_to_game() -> GameGenreRoutesToGameResult:
    from sidra_ai.creation.intent import detect_creation_intent

    checks = 0
    failures: list[str] = []

    for request, expected in _CASES:
        intent = detect_creation_intent(request)
        got = intent.kind.value if intent.is_creation else "not-creation"
        if got == expected:
            checks += 1
        else:
            failures.append(f"{request!r}: expected {expected}, got {got}")

    return GameGenreRoutesToGameResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=len(_CASES),
        failures=tuple(failures),
    )


__all__ = ["GameGenreRoutesToGameResult", "evaluate_game_genre_routes_to_game"]
