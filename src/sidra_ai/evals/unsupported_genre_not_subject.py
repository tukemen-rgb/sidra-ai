"""Are quiz/mahjong/card/board requests declined as genres, not drawn subjects?

C-1240: RPG, rhythm and tower-defense were declined as unsupported genres
(「〇〇型はまだ作れないため…いま作れるのは …」), but 「クイズゲーム」 and
「麻雀ゲーム」 fell through to the subject path (「『クイズ』の題材を描く型は
まだ無い」) - treated like 「猫」, a thing a template would draw. Quiz and
mahjong are game genres, and the subject path never lists what *can* be built,
so the user lost the one actionable hint. They were simply missing from the
GENRES table (which lists unsupported genres on purpose, to decline them).

The checks confirm each now declines as a genre with the buildable list, real
subjects still take the subject path, and a supported genre still builds.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass

_SUBJECT_MARK = "題材を描く型はまだ無い"
_GENRE_MARK = "型はまだ作れない"
_BUILDABLE = "いま作れるのは"


@dataclass(frozen=True)
class UnsupportedGenreResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _summary(request: str) -> str:
    from sidra_ai.creation.game_job import build_game_generator
    from sidra_ai.creation.intent import detect_creation_intent

    with tempfile.TemporaryDirectory() as tmp:
        return build_game_generator(tmp)(request, detect_creation_intent(request)).summary


def evaluate_unsupported_genre_not_subject() -> UnsupportedGenreResult:
    checks = 0
    failures: list[str] = []

    # Each newly-recognised genre must decline as a genre AND list what is
    # buildable, not fall to the "cannot draw this subject" path.
    for request in (
        "クイズゲームを作って",
        "麻雀ゲームを作って",
        "カードゲームを作って",
        "ボードゲームを作って",
    ):
        s = _summary(request)
        if _GENRE_MARK in s and _SUBJECT_MARK not in s:
            checks += 1
        else:
            failures.append(f"{request}: not declined as a genre")
        if _BUILDABLE in s:
            checks += 1
        else:
            failures.append(f"{request}: no buildable-genre list shown")

    # Regression: a real subject still takes the subject path.
    cat = _summary("猫のゲームを作って")
    if _SUBJECT_MARK in cat:
        checks += 1
    else:
        failures.append("猫: real subject lost its subject caveat")

    # Regression: a supported genre still builds without a decline.
    shooter = _summary("シューティングを作って")
    if _GENRE_MARK not in shooter and _SUBJECT_MARK not in shooter:
        checks += 1
    else:
        failures.append("シューティング: a supported genre was wrongly declined")

    return UnsupportedGenreResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=10,
        failures=tuple(failures),
    )
