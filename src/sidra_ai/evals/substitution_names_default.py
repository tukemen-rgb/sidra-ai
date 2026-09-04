"""Does a genre substitution call the fallback the default, not "the nearest"?

C-1230: 「格闘ゲームを作って」「ノベルゲームを作って」「音ゲーを作って」 all
returned 「…いちばん近い『タイミング釣り』型で作りました」. But the router
computes no nearness - every unsupported genre falls to the same default
template - so calling fishing 「いちばん近い」 (the nearest) to a fighting
game, a visual novel and a rhythm game alike was a claim of a resemblance
the code never measured. The wording now says 「代わりに既定の」 (the default,
instead), while still naming the genre asked for and the template built.

The checks build unsupported-genre and subject-only requests through the
generator and confirm the honest wording, with the genre name and built
title preserved.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass


@dataclass(frozen=True)
class SubstitutionNamesDefaultResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _summary(request: str) -> str:
    from sidra_ai.creation.game_job import build_game_generator
    from sidra_ai.creation.intent import detect_creation_intent

    with tempfile.TemporaryDirectory() as tmp:
        return build_game_generator(tmp)(request, detect_creation_intent(request)).summary


def evaluate_substitution_names_default() -> SubstitutionNamesDefaultResult:
    checks = 0
    failures: list[str] = []

    # Three unsupported genres, each landing on the same default - proof the
    # fallback is not a measured "nearest".
    for request, genre in (
        ("格闘ゲームを作って", "対戦格闘"),
        ("ノベルゲームを作って", "ノベル"),
        ("音ゲーを作って", "リズム"),
    ):
        s = _summary(request)
        if "いちばん近い" not in s and "一番近い" not in s:
            checks += 1
        else:
            failures.append(f"{request}: still claims 「いちばん近い」")
        if "代わりに既定の" in s:
            checks += 1
        else:
            failures.append(f"{request}: does not say it used the default")
        # The genre asked for is still named (C-1120), and the built template
        # too - the honesty of naming both must survive the reword.
        if genre in s and "タイミング釣り" in s:
            checks += 1
        else:
            failures.append(f"{request}: lost the genre name or the built type")

    # The subject-side substitution (「猫のゲーム」 -> default) is reworded too.
    subject = _summary("猫のゲームを作って")
    if "いちばん近い" not in subject and "代わりに既定の" in subject:
        checks += 1
    else:
        failures.append("subject substitution still claims 「いちばん近い」")

    return SubstitutionNamesDefaultResult(
        passed=not failures, checks_passed=checks, checks_total=10,
        failures=tuple(failures),
    )
