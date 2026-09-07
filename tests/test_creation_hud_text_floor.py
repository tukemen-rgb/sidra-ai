"""Every drawn word clears the type floor (§24, C-1375).

The canvas shrinks from its 720 design width on phones (§18), so the
floor sits where the smallest promoted screen (667px landscape, x0.926)
still clears iOS's smallest type: 13 canvas px is 12.0px effective,
above Caption 2's 11pt. Before this, three 11px and four 12px sites -
two of them shared preambles riding every template - dropped to 10.2px
and 11.1px on that screen.

The census is the paint: every font a frame can set is a string literal
in the page's script.
"""

from __future__ import annotations

import re

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.games import TEMPLATES

FLOOR = 13


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_every_drawn_word_clears_the_floor(template: str) -> None:
    html = generate_game("ゲームを作って", template=template).html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    sizes = [int(px) for px in re.findall(r"font='(\d+)px", script)]
    assert sizes, "the census found no drawn text at all"
    assert min(sizes) >= FLOOR, (
        f"{template} draws {min(sizes)}px text - "
        f"{min(sizes) * 0.926:.1f}px effective on a 667px landscape phone"
    )
