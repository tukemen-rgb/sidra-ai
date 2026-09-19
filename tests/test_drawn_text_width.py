"""Lines that a run does not reach, measured anyway (C-1966, §35).

``creation_drawn_text_stays_on_the_canvas`` plays each page and measures
every word it draws - the right question, and it reads 20/20. But a
reason line is only drawn on a loss the template can account for, and an
unattended 600-frame run does not lose every template. A longer English
line was measured going in with the judge staying at 20/20: a sabotage
that does not go red is evidence about the judge, so the lines it cannot
reach are held here instead.

The budget is the drawing context the strip really uses: ``round.py``
draws the reason centred at ``W/2`` in 13px monospace on a 720px canvas,
so a line may be 720px wide before either end leaves the screen.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.hudpaint import drawn_width
from sidra_ai.creation.recap import LOSS_WIRED, LOSS_WIRED_EN

#: The strip's own font size and canvas, from round.py's drawRoundStrip.
STRIP_PX = 13
STRIP_WIDTH = 720

#: A number long enough to be honest about: counts in these lines are
#: single or double digits in play, and the widest digit is one glyph.
SAMPLE = "88"


def _rendered(expression: str) -> str:
    """The sentence the expression builds, with the counters filled in.

    The expressions are JavaScript source spliced into the page, so this
    keeps the quoted pieces and puts a number where a counter goes.
    """

    import re

    pieces = re.findall(r"'([^']*)'", expression)
    joined = SAMPLE.join(pieces) if len(pieces) > 1 else "".join(pieces)
    return joined


@pytest.mark.parametrize("template", sorted(LOSS_WIRED_EN))
def test_english_reason_lines_fit_the_strip(template: str) -> None:
    for line in LOSS_WIRED_EN[template]:
        text = _rendered(line)
        width = drawn_width(text, STRIP_PX)
        assert width <= STRIP_WIDTH, f"{template}: {round(width)}px for {text!r}"


@pytest.mark.parametrize("template", sorted(LOSS_WIRED))
def test_japanese_reason_lines_fit_the_strip(template: str) -> None:
    for _count, line in LOSS_WIRED[template]["causes"]:
        text = _rendered(line)
        width = drawn_width(text, STRIP_PX)
        assert width <= STRIP_WIDTH, f"{template}: {round(width)}px for {text!r}"
