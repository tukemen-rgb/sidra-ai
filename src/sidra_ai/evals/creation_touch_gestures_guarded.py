"""Does the play surface take the phone's gestures, so a tap is a tap?

C-1535, filed 〔重大〕 and left unclaimed. The generated pages wire
``pointerdown/up/move/cancel`` but had no ``touch-action`` anywhere, and
pointer events do not stop the browser's own gestures. On a phone that meant
the game fought the page with the same finger that was trying to play it:

* a quick double tap zooms the page - and tapping IS the input in fishing,
  duel and kaiju, so playing them zooms the screen;
* a drag scrolls the page - and dragging IS the input in racing, catch and
  marble, which steer through ``padMove``/``pointermove``;
* a held finger selects and raises the magnifier over the surface.

None of this can appear in the node harness the other game judges use, which
is why ten rounds of review never saw it: node has no layout, no cascade and
no gestures. The filing said so and named the bar - 「生成ページの canvas/pad
要素に解決された計算値を見ること」 - because grepping for the property would
pass a rule written where it does not apply.

So this drives a real engine (:mod:`sidra_ai.creation.browser`) and reads
``getComputedStyle`` off the page as it ships. Both directions are checked,
because surrendering too much is its own defect:

* the canvas takes every gesture (``touch-action: none``) and refuses the
  long-press selection, on all ten templates;
* ``body`` keeps ``auto`` - the page must still scroll, and the viewport still
  allows pinch zoom, which C-1535 explicitly says not to take away;
* the panel's buttons are ``manipulation``, not ``none``: a finger that starts
  a scroll on a button should still scroll.

The virtual pad carries no rule of its own on purpose - C-1019 draws it inside
this canvas - so the eval asserts there is exactly one play surface rather than
looking for a second element that should not exist.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.browser import chromium_path, computed_styles
from sidra_ai.creation.games import TEMPLATES, generate_game

#: One request per template, so every shipped page is measured rather than a
#: representative one - the gesture is the input on six of the ten.
REQUESTS: dict[str, str] = {
    "fishing": "魚釣りゲームを作って",
    "catch": "フルーツキャッチを作って",
    "adventure": "迷宮を冒険するゲームを作って",
    "platformer": "ジャンプで進むゲームを作って",
    "puzzle": "パズルゲームを作って",
    "marble": "玉転がしゲームを作って",
    "racing": "レースゲームを作って",
    "duel": "光線で撃ち合う対戦ゲームを作って",
    "shooter": "シューティングゲームを作って",
    "kaiju": "巨大怪獣と戦うゲームを作って",
}

_PROPS = ("touch-action", "user-select", "-webkit-user-select")


@dataclass(frozen=True)
class TouchGesturesResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    #: True when no browser was available, so the caller reports the metric as
    #: unmeasurable instead of reporting a pass nobody verified.
    unmeasurable: bool = False


def evaluate_creation_touch_gestures_guarded() -> TouchGesturesResult:
    if chromium_path() is None:
        return TouchGesturesResult(
            passed=False,
            checks_passed=0,
            checks_total=0,
            failures=("no browser on this machine; resolved style unreadable",),
            unmeasurable=True,
        )

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    add(set(REQUESTS) == set(TEMPLATES),
        f"the template list and this eval disagree: "
        f"{sorted(set(TEMPLATES) ^ set(REQUESTS))}")

    for template in sorted(REQUESTS):
        page = generate_game(REQUESTS[template], template=template)
        # One play surface, and the pad is drawn inside it (C-1019).
        add(page.html.count("<canvas") == 1,
            f"{template}: {page.html.count('<canvas')} canvases, not one")
        styles = computed_styles(
            page.html,
            {"canvas": "canvas", "body": "body", "button": "button"},
            _PROPS,
        )
        if styles is None:
            failures.append(f"{template}: the browser did not answer")
            continue
        canvas = styles.get("canvas") or {}
        body = styles.get("body") or {}
        button = styles.get("button") or {}
        if not canvas:
            failures.append(f"{template}: no canvas matched on the page")
            continue
        # --- the surface takes the gestures ------------------------------
        add(canvas.get("touch-action") == "none",
            f"{template}: canvas touch-action is "
            f"{canvas.get('touch-action')!r}, so a tap is still a zoom")
        add("none" in (canvas.get("user-select"),
                       canvas.get("-webkit-user-select")),
            f"{template}: a held finger still selects over the canvas "
            f"({canvas.get('user-select')!r})")
        # --- and the page keeps its own -----------------------------------
        #     C-1535 says not to put this on body: scrolling and pinch zoom
        #     stay. Taking more than the surface is its own defect.
        add(body.get("touch-action") == "auto",
            f"{template}: body touch-action is {body.get('touch-action')!r} - "
            "the page can no longer be scrolled or pinched")
        if button:
            add(button.get("touch-action") == "manipulation",
                f"{template}: a panel button is "
                f"{button.get('touch-action')!r}, not manipulation")

    return TouchGesturesResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )
