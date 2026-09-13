"""Do the game's keys stay in the game instead of scrolling the page?

C-1215: the browser's default for arrows and Space is scrolling, so walking
south in the adventure pushed the board off screen - 208px in six presses,
and every template shares the shell. The guard rides the native listener
before the remap wrapper exists, and excludes form controls so the tuning
panel's sliders keep their arrow keys. Since C-1759 it asks the remap at
press time as well, so a key somebody re-assigned is guarded too - the
behavioural halves of that are driven in
``creation_bound_keys_dont_scroll``.

Scrolling itself needs a browser, so the mechanics are pinned on generated
pages across templates; the end-to-end proof (scrollY staying 0 through
arrow and Space presses; a range input's keydown left unprevented) ran in a
real browser at fix time and is recorded in the loop log.
"""

from __future__ import annotations

from dataclasses import dataclass

_GUARD_MARKS = (
    "INPUT|TEXTAREA|SELECT|BUTTON",
    "' ','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'",
    # C-1759 moved the decision behind a name. The five literals above are
    # still in the page - they are the keys the product ships with - but
    # the guard now asks whether THIS page acts on the key, so that a key
    # an operator re-assigned loses its default too. Pinning the old
    # spelling would have meant pinning the bug: a bound PageDown drove
    # the game and scrolled the board away, which is the 208px this eval
    # exists about.
    "function keyDrivesGame(",
    "if(keyDrivesGame(e))e.preventDefault()",
)


@dataclass(frozen=True)
class KeysDontScrollResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_keys_dont_scroll() -> KeysDontScrollResult:
    from sidra_ai.creation.games import TEMPLATES, generate_game

    checks = 0
    failures: list[str] = []
    probes = ("adventure", "puzzle", "shooter", "fishing")

    for key in probes:
        html = generate_game("ゲームを作って", template=key).html
        if all(mark in html for mark in _GUARD_MARKS):
            checks += 1
        else:
            failures.append(f"{key}: the scroll guard is missing")

    if all(key in TEMPLATES for key in probes):
        checks += 1
    else:
        failures.append("a probed template no longer exists")

    return KeysDontScrollResult(
        passed=not failures, checks_passed=checks, checks_total=len(probes) + 1,
        failures=tuple(failures),
    )
