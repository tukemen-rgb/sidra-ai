"""Does 「難易度を上げて／下げて」 change a game's difficulty like 「難しく／簡単に」?

C-1470. The revision detector recognised the *adjectival* difficulty words
(「難しく」「簡単に」「速く」「遅く」) but not the most explicit idiom a player
reaches for right after making a game - 「これの難易度を上げて」「難易度を下げて」
「難易度を高くして」. Two gaps caused it: the adjustment vocabulary named no
「難易度を上げ／下げ／高く／低く」 form, and the change-verb gate (which lets a
revision through) listed して/変えて/やめて but not 上げて／下げて, so 「難易度を
上げて」 - an instruction with no して in it, exactly the case C-1117's
やめて／止めて addressed - was vetoed as not-an-instruction.

Both are now recognised. The ambiguous 「レベルを上げて」 still maps to no
difficulty change, the band/theme/accent axes are untouched, and the
back-reference requirement is unchanged. The checks call the real detector.
"""

from __future__ import annotations

from dataclasses import dataclass

# Explicit "raise the difficulty" - must become difficulty +1.
_HARDER = (
    "これの難易度を上げて",
    "これの難易度を上げる",
    "これの難易度をあげて",
    "これの難易度を高くして",
    "これの難易度を上げてもらえますか",  # polite request composes (C-1463)
)

# Explicit "lower the difficulty" - must become difficulty -1.
_EASIER = (
    "これの難易度を下げて",
    "これの難易度を下げる",
    "これの難易度をさげて",
    "これの難易度を低くして",
)

# Regressions: the adjectival forms still work, the ambiguous "raise the level"
# maps to no difficulty change, and the band axis is not pulled into difficulty.
_STILL_HARDER = ("これを難しくして",)
_STILL_EASIER = ("これを簡単にして",)
_NOT_DIFFICULTY = ("これのレベルを上げて",)   # no difficulty adjustment at all
_BAND_NOT_DIFFICULTY = ("これの敵を増やして",)  # band +1, never difficulty


@dataclass(frozen=True)
class RevisionDifficultyResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_revision_difficulty_idiom() -> RevisionDifficultyResult:
    from sidra_ai.creation.revise import detect_revision_intent

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for m in (*_HARDER, *_STILL_HARDER):
        intent = detect_revision_intent(m)
        add(intent.is_revision and intent.adjustments.get("difficulty") == "+1",
            f"{m!r} did not become difficulty+1: rev={intent.is_revision}, adj={intent.adjustments}")

    for m in (*_EASIER, *_STILL_EASIER):
        intent = detect_revision_intent(m)
        add(intent.is_revision and intent.adjustments.get("difficulty") == "-1",
            f"{m!r} did not become difficulty-1: rev={intent.is_revision}, adj={intent.adjustments}")

    for m in _NOT_DIFFICULTY:
        intent = detect_revision_intent(m)
        add("difficulty" not in intent.adjustments,
            f"{m!r} wrongly changed difficulty: adj={intent.adjustments}")

    for m in _BAND_NOT_DIFFICULTY:
        intent = detect_revision_intent(m)
        add(intent.adjustments.get("band") == "+1" and "difficulty" not in intent.adjustments,
            f"{m!r} did not stay a band-only change: adj={intent.adjustments}")

    total = (len(_HARDER) + len(_STILL_HARDER) + len(_EASIER) + len(_STILL_EASIER)
             + len(_NOT_DIFFICULTY) + len(_BAND_NOT_DIFFICULTY))
    return RevisionDifficultyResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["RevisionDifficultyResult", "evaluate_revision_difficulty_idiom"]
