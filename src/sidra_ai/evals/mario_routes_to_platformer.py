"""Does a franchise-platformer request build a platformer, name guarded?

C-1225: 「マリオみたいなゲーム」 detected no genre and fell to the default
fishing template with no notice, even though マリオ was already in the
trademark guard. ゼルダ routes to adventure the same way - the flagship of a
genre names the genre - so マリオ now routes to the platformer, and the title
guard swaps the name for an original one. 「マリオカートのレース」 still lands
on racing, which is named before the platformer.

The checks route franchise requests through the public ``choose_template`` /
``detect_genre`` and build one through the generator to confirm the template
is the platformer, the artifact carries no trademark, and a race request
that merely mentions the franchise still routes to racing.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass

_MARIO_REQUESTS = (
    "マリオみたいなゲームを作って",
    "マリオ風のゲーム",
    "マリオっぽいゲーム",
)


@dataclass(frozen=True)
class MarioRoutesResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_mario_routes_to_platformer() -> MarioRoutesResult:
    from sidra_ai.creation.game_job import build_game_generator
    from sidra_ai.creation.games import choose_template, detect_genre, generate_game
    from sidra_ai.creation.intent import detect_creation_intent

    checks = 0
    failures: list[str] = []

    for request in _MARIO_REQUESTS:
        if choose_template(request) == "platformer":
            checks += 1
        else:
            failures.append(f"{request}: routed to {choose_template(request)}, not platformer")

    named = detect_genre("マリオみたいなゲームを作って")
    if named is not None and named.template == "platformer":
        checks += 1
    else:
        failures.append("a マリオ request is not a detected genre (summary would stay silent)")

    # A race request that only mentions the franchise keeps racing, matched
    # before the platformer.
    if choose_template("マリオカートみたいなレースゲーム") == "racing":
        checks += 1
    else:
        failures.append("マリオカート race stolen from racing by the platformer word")

    # The built artifact is a platformer and carries no trademark, with the
    # substitution said out loud.
    with tempfile.TemporaryDirectory() as tmp:
        outcome = build_game_generator(tmp)(
            "マリオみたいなゲームを作って",
            detect_creation_intent("マリオみたいなゲームを作って"),
        )
    if outcome.details.get("built_template") == "platformer":
        checks += 1
    else:
        failures.append(f"built {outcome.details.get('built_template')}, not platformer")

    game = generate_game("マリオみたいなゲームを作って")
    if "マリオ" not in game.html:
        checks += 1
    else:
        failures.append("the generated artifact carries the trademark")
    if "オリジナル版" in game.tagline:
        checks += 1
    else:
        failures.append("the substitution is not stated on the artifact")

    return MarioRoutesResult(
        passed=not failures, checks_passed=checks,
        checks_total=len(_MARIO_REQUESTS) + 5,
        failures=tuple(failures),
    )
