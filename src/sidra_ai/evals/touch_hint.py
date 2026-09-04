"""Does a generated game tell a phone user it can be played by touch?

C-1229: the how-to and the start briefing name keyboard keys (「← →」), but a
phone has none, and the on-screen pad (◀ ▶ / A) appears only once play
starts. Before that a touch visitor is told to press keys they cannot. The
page shell now carries a one-line hint that names the pad, shown only for a
coarse pointer so the desktop keeps its keyboard story.

Layout cannot be computed offline, so the checks pin the mechanics on the
game source; the end-to-end proof (the hint display:block under iPhone
emulation, none on desktop) ran at fix time and is recorded in the loop log.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TouchHintResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_touch_hint() -> TouchHintResult:
    from sidra_ai.creation.games import generate_game

    html = generate_game("魚を釣るゲーム").html

    checks = 0
    failures: list[str] = []

    if 'class="touchhint"' in html:
        checks += 1
    else:
        failures.append("no touch hint element on the page")

    # The hint names touch operation, not another key.
    m = re.search(r'class="touchhint">([^<]*)<', html)
    hint_text = m.group(1) if m else ""
    if "画面のボタン" in hint_text or "タッチ" in hint_text:
        checks += 1
    else:
        failures.append("the hint does not tell the user they can touch/tap to play")

    # Hidden by default, shown only under a coarse pointer.
    if ".touchhint{display:none" in html:
        checks += 1
    else:
        failures.append("the hint is not hidden by default")
    if re.search(r"@media\s*\(pointer:coarse\)\s*\{\s*\.touchhint\{display:block\}", html):
        checks += 1
    else:
        failures.append("the hint is not shown under a coarse pointer")

    # It rides every template (shell-level), so a puzzle carries it too.
    if 'class="touchhint"' in generate_game("パズルを作って").html:
        checks += 1
    else:
        failures.append("the hint does not ride every template")

    return TouchHintResult(
        passed=not failures, checks_passed=checks, checks_total=5,
        failures=tuple(failures),
    )
