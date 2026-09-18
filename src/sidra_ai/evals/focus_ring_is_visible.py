"""Can a keyboard user see where they are on a generated page?

C-1950, §39. The page a request produces has controls - the fullscreen
button, and every input the tuning panel builds - and until this item it
said **nothing at all** about focus: no ``:focus``, no ``:focus-visible``,
anywhere in the shell. What a keyboard user saw was whatever the engine
decided to draw.

That is not a small omission on this product. WCAG SC 2.4.7 (Level AA)
requires a mode of operation where the keyboard focus indicator is visible,
and SC 2.4.13 asks the indicator to be at least the area of a 2px perimeter
of the control and to differ from the unfocused state by 3:1. 2.4.13's own
exemption is written for pages that leave it to the user agent - which is
precisely the state this page was in, on a product whose four themes are
three-quarters dark. Measured before the fix, through headless Chromium:
``outline-style: auto``, ``outline-color: rgb(16,16,16)``, on a control
whose background is ``rgb(12,19,34)`` - 1.03:1 as computed.

**What this counts.** Themes whose focused control carries an indicator
this eval can measure and that clears the bar, out of every theme the
registry has. Four rules per theme, all read off the real page in a real
browser (C-1640):

1. The page declares an outline of its own - ``solid``, not ``auto`` and
   not ``none``. ``auto`` is the engine's ring: it may well be drawn, and
   it may well be two-tone, but what it is cannot be read from the page,
   and a promise that cannot be read is not one this loop counts.
2. It is at least 2px, the perimeter 2.4.13 asks for.
3. It is offset from the control, so the ring is not painted over the
   border it sits on.
4. Its colour clears 3:1 against the control's own background.

Every theme is measured, not one. C-1945 is where a judge that generated a
single production let nine templates' rows ship untranslated, and the
lesson was cheap to apply here: the themes are the thing the ring's
contrast depends on, so the themes are what this iterates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The minimum the indicator must clear against the control it marks
#: (WCAG 1.4.11 non-text contrast, and 2.4.13's focused/unfocused ratio).
MINIMUM_RATIO = 3.0

#: The perimeter 2.4.13 asks for.
MINIMUM_WIDTH_PX = 2.0


@dataclass(frozen=True)
class FocusRingResult:
    themes_with_a_visible_ring: int
    themes_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()
    measured: bool = True


def _rgb(value: str) -> tuple[int, int, int] | None:
    numbers = re.findall(r"\d+(?:\.\d+)?", value or "")
    if len(numbers) < 3:
        return None
    return tuple(int(float(n)) for n in numbers[:3])  # type: ignore[return-value]


def _luminance(colour: tuple[int, int, int]) -> float:
    def channel(raw: int) -> float:
        value = raw / 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = colour
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)

def _ratio(one: tuple[int, int, int], two: tuple[int, int, int]) -> float:
    first, second = _luminance(one), _luminance(two)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def evaluate_focus_ring_is_visible() -> FocusRingResult:
    from sidra_ai.creation.browser import chromium_path, computed_styles
    from sidra_ai.creation.games import generate_game
    from sidra_ai.creation.themes import THEMES

    if chromium_path() is None:
        # Honest rather than green: with no browser there is no measurement,
        # and a pass invented here would be the judge speaking for a page it
        # never opened.
        return FocusRingResult(0, len(THEMES), ("no browser to measure with",), (), False)

    failures: list[str] = []
    readings: list[str] = []
    right = 0

    for key in sorted(THEMES):
        theme = THEMES[key]
        # Asked for the way the product wants a theme asked for: a theme cue
        # AND one of the theme's own words (`select_theme` requires both, for
        # the same reason the intent parser requires a verb and an artifact).
        # Measured while this was written - the first draft asked with the
        # word alone, every page came back gameyard, and all four themes
        # reported the same 12.26 ratio. A judge that iterates four names and
        # measures one page is the shape C-1945 caught, and it caught this
        # one too, one item later.
        request = f"テーマを{theme.words[0]}にしてゲームを作って"
        game = generate_game(request)
        # Checked on the page rather than by asking the chooser: the accent
        # is in the stylesheet the browser will read, and each theme's is
        # distinct. A request that did not change the theme is a failure
        # here, not a silently repeated measurement.
        if theme.tokens["accent"].casefold() not in game.html.casefold():
            failures.append(
                f"{key}: 「{request}」 did not produce this theme - its ring "
                "is never the one a reader sees"
            )
            continue
        # The button ships hidden (it is shown when fullscreen is available),
        # so it is revealed and focused before the styles are read. Focusing
        # it is what a keyboard user does; revealing it is what the page does
        # on a browser that offers fullscreen.
        page = game.html.replace(
            "</body>",
            "<script>var b=document.querySelector('.fullbtn');"
            "if(b){b.style.display='inline-block';b.focus()}</script></body>",
        )
        styles = computed_styles(
            page,
            {"button": ".fullbtn"},
            (
                "outline-width",
                "outline-style",
                "outline-color",
                "outline-offset",
                "background-color",
            ),
        )
        read = (styles or {}).get("button") or {}
        if not read:
            failures.append(f"{key}: the page has no control to focus")
            continue

        style = read.get("outline-style", "")
        width = float(re.sub(r"[^\d.]", "", read.get("outline-width", "0") or "0") or 0)
        offset = float(re.sub(r"[^\d.\-]", "", read.get("outline-offset", "0") or "0") or 0)
        ring = _rgb(read.get("outline-color", ""))
        background = _rgb(read.get("background-color", ""))
        ratio = _ratio(ring, background) if ring and background else 0.0
        readings.append(
            f"{key} {style} {width:g}px offset={offset:g} ratio={ratio:.2f}"
        )

        problems: list[str] = []
        if style != "solid":
            problems.append(
                f"the page draws no ring of its own (outline-style: {style or 'none'})"
            )
        if width < MINIMUM_WIDTH_PX:
            problems.append(f"the ring is {width:g}px, under the 2px perimeter")
        if offset <= 0:
            problems.append("the ring sits on the control's own border, not outside it")
        if ratio < MINIMUM_RATIO:
            problems.append(f"the ring is {ratio:.2f}:1 against the control")
        if problems:
            failures.append(f"{key}: " + "; ".join(problems))
        else:
            right += 1

    return FocusRingResult(
        themes_with_a_visible_ring=right,
        themes_total=len(THEMES),
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = ["FocusRingResult", "evaluate_focus_ring_is_visible", "MINIMUM_RATIO"]
