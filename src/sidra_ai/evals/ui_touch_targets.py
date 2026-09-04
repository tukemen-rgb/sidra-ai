"""Are the ask page's buttons big enough to tap on a phone?

C-1224: on an iPhone-sized screen the 更新 button and every per-file 開く
download button came out 41-42px tall - under the 48dp minimum a touch
target needs. This is the page an author opens on a phone to grab a
generated file, and C-1219's fix was on the game shell, a different file.
No button on this page sets a height, so one rule scoped to a coarse
pointer lifts them all without touching the desktop layout.

Layout cannot be computed offline, so the check pins the rule on the page
CSS; the end-to-end proof (every button 48px under iPhone emulation, desktop
unchanged) ran at fix time and is recorded in the loop log.
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
class UiTouchTargetsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_touch_targets() -> UiTouchTargetsResult:
    from sidra_ai.api.ui import ASK_PAGE

    checks = 0
    failures: list[str] = []

    coarse = _COARSE_BLOCK.search(ASK_PAGE)
    if coarse:
        checks += 1
    else:
        failures.append("no coarse-pointer media query on the ask page")

    body = coarse.group("body") if coarse else ""
    match = _MIN_HEIGHT.search(body)
    if match:
        checks += 1
    else:
        failures.append("no button min-height inside the coarse-pointer query")

    if match and int(match.group(1)) >= 48:
        checks += 1
    else:
        failures.append("button min-height is below the 48dp minimum")

    # Must stay inside the coarse query, so the desktop layout is untouched.
    outside = re.sub(_COARSE_BLOCK.pattern, "", ASK_PAGE, flags=re.DOTALL)
    style = outside.split("</style>", 1)[0]
    if "min-height" not in style.split("button {", 1)[-1][:200]:
        checks += 1
    else:
        failures.append("a button min-height applies outside the coarse-pointer query")

    return UiTouchTargetsResult(
        passed=not failures, checks_passed=checks, checks_total=4,
        failures=tuple(failures),
    )
