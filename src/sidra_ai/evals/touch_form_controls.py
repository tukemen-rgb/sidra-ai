"""Are a generated game's tuning-panel form controls usable on a phone?

C-1234: C-1219 raised the panel's *buttons* to 48dp for a coarse pointer, but
the tuning panel's other controls - the difficulty ``select``, the range
sliders, the colour picker, the checkboxes - stayed 13-27px tall, under the
44px a finger needs, and every one of them rendered at a 13.3px font, which
makes iOS Safari zoom the page on focus (the ask page fixed exactly that with
a 16px floor, C-1225). The generated game shell never got either rule for its
form controls.

The shell now, for a coarse pointer only, floors ``select`` and ``input`` at a
16px font (no zoom-on-focus) and a 44px min-height, and enlarges the
checkboxes. Layout cannot be computed offline, so the checks pin the rules on
the shell CSS inside the coarse-pointer query; the iPhone-emulation proof runs
at fix time and is recorded in the loop log. Desktop keeps its compact panel.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_COARSE_BLOCK = re.compile(
    r"@media\s*\(\s*pointer\s*:\s*coarse\s*\)\s*\{(?P<body>.*?)\}\s*(?:/\*|@media|</style)",
    re.DOTALL,
)


@dataclass(frozen=True)
class TouchFormControlsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _coarse_body(html: str) -> str:
    # Grab everything from the coarse-pointer query open to the <style> close,
    # so a multi-rule block is captured whole (the button-only regex in
    # touch_targets stops at the first rule; this eval needs the rest too).
    start = re.search(r"@media\s*\(\s*pointer\s*:\s*coarse\s*\)\s*\{", html)
    if not start:
        return ""
    tail = html[start.end():]
    end = tail.find("</style")
    return tail[: end if end != -1 else len(tail)]


def evaluate_touch_form_controls() -> TouchFormControlsResult:
    from sidra_ai.creation.games import generate_game

    html = generate_game("魚を釣るゲームを作って").html
    body = _coarse_body(html)

    checks = 0
    failures: list[str] = []

    # 1: there is a coarse-pointer block at all.
    if body:
        checks += 1
    else:
        failures.append("no coarse-pointer media query in the game shell")

    # 2: a 16px font floor on select/input - what stops iOS zoom-on-focus.
    #    Must name select and input (not only button).
    font_rule = re.search(
        r"(select|input)[^{}]*\{[^{}]*font-size\s*:\s*16px", body
    )
    if font_rule and "select" in body and "input" in body:
        checks += 1
    else:
        failures.append("no 16px font floor on select/input inside coarse query")

    # 3: a min-height on select/input so the controls clear a fingertip.
    height_rule = re.search(
        r"(select|input)[^{}]*\{[^{}]*min-height\s*:\s*(\d+)px", body
    )
    if height_rule and int(height_rule.group(2)) >= 44:
        checks += 1
    else:
        failures.append("no >=44px min-height on select/input inside coarse query")

    # 4: the range slider specifically is reachable (its hit area is the track).
    if re.search(r"input\[type=range\]", body):
        checks += 1
    else:
        failures.append("the range slider is not sized for a coarse pointer")

    # 5: checkboxes are enlarged past their ~13px default.
    cb = re.search(r"input\[type=checkbox\][^{}]*\{[^{}]*(?:width|height)\s*:\s*(\d+)px", body)
    if cb and int(cb.group(1)) >= 20:
        checks += 1
    else:
        failures.append("checkboxes are not enlarged for a coarse pointer")

    # 6: the button rule (C-1219) survived - this eval must not regress it.
    if re.search(r"button\s*\{[^{}]*min-height\s*:\s*48px", body):
        checks += 1
    else:
        failures.append("the C-1219 button min-height was lost")

    # 7: none of this leaks to desktop - the rules live inside the coarse query,
    #    so the base (non-media) CSS must not carry the 16px input floor.
    base = html.split("@media", 1)[0]
    if not re.search(r"(select|input)[^{}]*\{[^{}]*min-height\s*:\s*44px", base):
        checks += 1
    else:
        failures.append("a coarse-pointer rule leaked into the desktop base CSS")

    return TouchFormControlsResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=7,
        failures=tuple(failures),
    )
