"""Does the on-screen pad provide every control the briefing tells you to press?

C-1247 (a C-1244 regression): C-1244 made the pad draw only the keys
``touchpad.keys_read`` reports, and ``keys_read`` cannot see two of the three
ways a template reads a key - ``K('ArrowLeft')`` (platformer's helper) and
``partsSteerX(...)`` (kaiju's shared steering). So the pad dropped ◀▶ for those
games while their briefing still said 「← → で歩き／走り」: on a phone they could
not be moved at all.

This check is deliberately independent of ``keys_read`` - it reads the promise
the player is shown. For every genre it takes the briefing's 操作 line, and for
every arrow (←→↑↓, or 「矢印」 for all four) or SPACE it names, requires the
generated ``PAD_ACTIVE`` to contain the matching pad key. A control the game
tells you to use that the pad does not offer is the failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_GLYPH = {"←": "ArrowLeft", "→": "ArrowRight", "↑": "ArrowUp", "↓": "ArrowDown"}

#: Requests that route to each template. English names route by the genre key
#: except 「marble」, which the router reads as a fishing word (an unrelated
#: routing quirk), so the marble template is asked for by name.
_REQUEST_OVERRIDE = {"marble": "マーブル を作って"}


@dataclass(frozen=True)
class PadCoversBriefingControlsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _pad_active(script: str) -> set[str]:
    m = re.search(r"PAD_ACTIVE\s*=\s*new Set\(\s*\[([^\]]*)\]\s*\)", script)
    if m is None:
        return set()
    return {tok for tok in re.findall(r"""["']((?:\\.|[^"'\\])*)["']""", m.group(1))}


def _required_from_briefing(op_line: str) -> set[str]:
    req: set[str] = set()
    for glyph, key in _GLYPH.items():
        if glyph in op_line:
            req.add(key)
    if "矢印" in op_line:
        req |= set(_GLYPH.values())
    if "SPACE" in op_line:
        req.add(" ")
    return req


def evaluate_pad_covers_briefing_controls() -> PadCoversBriefingControlsResult:
    from sidra_ai.creation.games import TEMPLATES, _script_of, generate_game
    from sidra_ai.creation.startscreen import BRIEFINGS

    checks = 0
    total = 0
    failures: list[str] = []

    for genre in sorted(TEMPLATES):
        briefing = BRIEFINGS.get(genre)
        if not briefing or len(briefing) < 2:
            continue
        required = _required_from_briefing(briefing[1])
        if not required:
            continue
        total += 1
        request = _REQUEST_OVERRIDE.get(genre, f"{genre} を作って")
        game = generate_game(request)
        # Only judge a game that actually built its own template - a routing
        # miss would silently test the wrong page.
        if game.template != genre:
            failures.append(f"{genre}: request routed to {game.template}")
            continue
        active = _pad_active(_script_of(game.html))
        missing = required - active
        if not missing:
            checks += 1
        else:
            failures.append(
                f"{genre}: briefing shows {sorted(required)} but pad lacks "
                + ",".join(sorted(missing))
            )

    return PadCoversBriefingControlsResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "PadCoversBriefingControlsResult",
    "evaluate_pad_covers_briefing_controls",
]
