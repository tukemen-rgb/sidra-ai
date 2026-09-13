"""Does the generative-art HTML say on the page that a requested colour was not applied?

C-1786. The art palette is fixed to the brand (cyan on magenta), so 「青い海のアート」
is drawn in that palette, not blue. The chat summary says so (C-1272), and the page
already self-discloses the *pattern* default (C-1284/C-1283) - but the *colour*-not-
applied fact lived only in the chat summary. A user who reopens or forwards the HTML
(the artifact) sees a page titled 「青い…」 in the wrong palette with no word of it.

``generate_art`` now carries the colour caveat on the page too, alongside the pattern
note. The checks read the real ``generate_art`` HTML and the ``art_job`` summary.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass

from sidra_ai.creation.art import generate_art
from sidra_ai.creation.art_job import build_art_generator
from sidra_ai.creation.intent import detect_creation_intent

_COLOR_NOTE = "配色に反映していません"
_FIXED = "固定の配色"
_PATTERN_DEFAULT = "既定の"


@dataclass(frozen=True)
class ArtColorPageResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_art_page_discloses_color_not_applied() -> ArtColorPageResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    coloured = generate_art("青い螺旋のアートを作って").html      # colour + no pattern named
    plain = generate_art("螺旋のアートを作って").html            # no colour
    coloured_pat = generate_art("青い軌道のアートを作って").html  # colour + pattern named (軌道)

    # --- (A) a colour request discloses non-application on the page ------
    add(_COLOR_NOTE in coloured,
        "A: the art page does not say the requested colour was not applied")
    # --- (B) ...and names the fixed palette ------------------------------
    add(_FIXED in coloured, "B: the art page does not name the fixed palette")
    # --- (C) a colourless request adds no such note (no false positive) --
    add(_COLOR_NOTE not in plain,
        "C: a colourless art request wrongly claims a colour was dropped")
    # --- (D) the pattern-default note (C-1284) still coexists ------------
    add(_PATTERN_DEFAULT in coloured,
        "D: the pattern-default page note (C-1284) regressed")
    # --- (E) the chat summary still carries the colour caveat (C-1272) ---
    gen = build_art_generator(tempfile.mkdtemp())
    outcome = gen("青い螺旋のアートを作って", detect_creation_intent("青い螺旋のアートを作って"))
    summary = getattr(outcome, "summary", "") or ""
    add(_COLOR_NOTE in summary, "E: the chat summary lost its colour caveat")
    # --- (F) a named-pattern colour request still discloses colour -------
    #         (colour is independent of the pattern; and no pattern-default note)
    add(_COLOR_NOTE in coloured_pat and _PATTERN_DEFAULT not in coloured_pat,
        "F: a named-pattern colour request dropped the colour note or added a stray default note")

    total = 6
    return ArtColorPageResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ArtColorPageResult",
    "evaluate_art_page_discloses_color_not_applied",
]
