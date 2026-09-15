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
#: Every 「selector { ... min-height: Npx ... }」 rule, selector captured. The
#: selector used to be required to be exactly 「button {」, so when the rule grew
#: to 「button, input { min-height: 48px }」 - the same 48px, now lifting the
#: text inputs too - this read it as 「no button min-height inside the
#: coarse-pointer query」 and turned the whole suite red against a page that
#: satisfies the rule (found 2026-09-15 while C-1535 was in flight; the ask
#: page had been correct the whole time).
#:
#: Which member of the list it is cannot be decided by a regex without letting
#: 「.tool button」 in, so the rule is found here and judged in
#: :func:`_raises_every_button` below - the check is about EVERY button, and a
#: descendant or class selector raises some of them.
_MIN_HEIGHT = re.compile(
    r"(?P<sel>[^{}]+)\{[^}]*min-height\s*:\s*(?P<px>\d+)px",
    re.DOTALL,
)


def _raises_every_button(selector: str) -> bool:
    """Does this selector list lift buttons as such, not just some of them?"""

    return any(part.strip() == "button" for part in selector.split(","))


def _button_floor(body: str) -> int | None:
    """The min-height every button in ``body`` is held to, if any."""

    for rule in _MIN_HEIGHT.finditer(body):
        if _raises_every_button(rule.group("sel")):
            return int(rule.group("px"))
    return None


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
    floor = _button_floor(body)
    if floor is not None:
        checks += 1
    else:
        failures.append("no button min-height inside the coarse-pointer query")

    if floor is not None and floor >= 48:
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
