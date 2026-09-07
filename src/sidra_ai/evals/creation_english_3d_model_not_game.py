"""Does an English "3D model" request route to the 3D generator, not a game?

C-1479. ``GAME_WORDS`` carries "3d", and MODEL3D's cues "3d model"/"3d" match at
the same index, so 「make a 3D model」 tied GAME and MODEL3D at one position.
``_find_artifact`` breaks a same-position tie by dict order, and GAME is listed
before MODEL3D, so an English 3D-model request built a fishing game instead - the
wrong kind of artifact entirely. Japanese escaped it only because its 「モデル」
cue sits after 「3d」 and wins by the latest-position rule; English has no such
trailing "model" cue.

The tie-break now prefers the longer (more specific) cue at an equal position,
so "3d model" beats "3d". A request where a game word appears *later* than "3d"
(「3Dゲーム」, "make a 3d game") still routes to GAME by position - a 3D game is a
game - because that is not a tie.

The checks read ``detect_creation_intent`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.intent import detect_creation_intent


def _kind(message: str) -> str:
    return detect_creation_intent(message).kind.value


@dataclass(frozen=True)
class English3DModelResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_creation_english_3d_model_not_game() -> English3DModelResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # English 3D-model requests route to the 3D generator.
    for m in ("make a 3D model", "build a 3D model of a house",
              "create a 3d model of a car"):
        add(_kind(m) == "model3d", f"{m!r}: routed to {_kind(m)}, not model3d")

    # Japanese 3D-model requests are unchanged.
    for m in ("3Dモデルを作って", "魚の3Dモデルを作って"):
        add(_kind(m) == "model3d", f"{m!r}: routed to {_kind(m)}, not model3d")

    # A 3D *game* is still a game - a later game word wins by position, no tie.
    for m in ("3Dゲームを作って", "make a 3d game"):
        add(_kind(m) == "game", f"{m!r}: routed to {_kind(m)}, not game")

    # Other kinds are unaffected by the tie-break change.
    add(_kind("make a fishing game") == "game", "English fishing game misrouted")
    add(_kind("create a pitch deck") == "deck", "English pitch deck misrouted")
    add(_kind("ゲームを企画から作って") == "project", "project position tie-break regressed")

    total = 10
    return English3DModelResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["English3DModelResult", "evaluate_creation_english_3d_model_not_game"]
