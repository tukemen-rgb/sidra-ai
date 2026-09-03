"""Are a generated game's control-panel buttons big enough to tap on a phone?

C-1219: the game itself became playable on a phone once the touch pad
synthesised key events (touchpad.py), but the HTML control panel around it
- skin picker, copy-result, key remap, reset - kept buttons 24-32px tall.
The knowledge base the pad itself cites (game-design-notes.md #4) sets a
48dp minimum with 8dp spacing; the panel ignored it. Fingers are ~44px
wide, so the controls right next to a now-playable game mis-tapped.

No panel sets a button height inline, so one rule in the shared page shell,
scoped to a coarse pointer, raises every button at once without touching
the desktop layout or the canvas-drawn pad. Layout cannot be computed
offline, so the checks pin the rule on the shell CSS; the end-to-end proof
(every button 48px under iPhone emulation, desktop unchanged) ran at fix
time and is recorded in the loop log.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_COARSE_BLOCK = re.compile(
    r"@media\s*\(\s*pointer\s*:\s*coarse\s*\)\s*\{(?P<body>.*?\})\s*\}",
    re.DOTALL,
)
_MIN_HEIGHT = re.compile(r"button\s*\{[^}]*min-height\s*:\s*(\d+)px", re.DOTALL)


@dataclass(frozen=True)
class TouchTargetsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_touch_targets() -> TouchTargetsResult:
    from sidra_ai.creation.games import generate_game

    html = generate_game("魚を釣るゲームを作って").html

    checks = 0
    failures: list[str] = []

    coarse = _COARSE_BLOCK.search(html)
    if coarse:
        checks += 1
    else:
        failures.append("no coarse-pointer media query in the game shell")

    # The tap-target rule must live inside the coarse-pointer query, so the
    # desktop layout keeps its compact controls.
    body = coarse.group("body") if coarse else ""
    match = _MIN_HEIGHT.search(body)
    if match:
        checks += 1
    else:
        failures.append("no button min-height inside the coarse-pointer query")

    if match and int(match.group(1)) >= 48:
        checks += 1
    else:
        failures.append("button min-height is below the 48dp knowledge-base minimum")

    # It must not leak into the unconditional CSS - a desktop min-height
    # would inflate the compact panel the harsh review did not complain about.
    outside = re.sub(_COARSE_BLOCK.pattern, "", html, flags=re.DOTALL)
    if "min-height" not in re.sub(r"<script.*?</script>", "", outside, flags=re.DOTALL):
        checks += 1
    else:
        failures.append("a button min-height applies outside the coarse-pointer query")

    return TouchTargetsResult(
        passed=not failures, checks_passed=checks, checks_total=4,
        failures=tuple(failures),
    )
