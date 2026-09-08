"""The message stays long enough to read (§4 増築, C-1395).

say() gave every message a flat 140/150 frames, so the 22-char door hint
left at 9.4 chars/second - 2.4x the Japanese subtitle standard (Netflix
TTSG I.19: up to 4 characters per second). Now the display time knows the
character count: 15 frames a character with the old flat count as the
floor, so short lines are bit-identical to what they always were.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.adventure import say_probe as adventure_say
from sidra_ai.creation.platformer import say_probe as platformer_say

_PROBES = {"adventure": adventure_say, "platformer": platformer_say}
_FLOORS = {"adventure": 140, "platformer": 150}


def _drive(template: str) -> tuple[dict, str, str]:
    html = generate_game("ゲームを作って", template=template).html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    lits = re.findall(r"say\('([^']+)'\)", script)
    short, long = min(lits, key=len), max(lits, key=len)
    run = subprocess.run(
        ["node", "-"],
        input=_PROBES[template](script, short=short, long=long),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1]), short, long


@pytest.mark.parametrize("template", ["adventure", "platformer"])
def test_short_lines_keep_the_old_flat_count(template: str) -> None:
    got, short, _ = _drive(template)
    want = max(_FLOORS[template], len(short) * 15)
    assert got["shortShown"] == want, "the short line's timing changed"


@pytest.mark.parametrize("template", ["adventure", "platformer"])
def test_the_longest_line_meets_four_chars_per_second(template: str) -> None:
    got, _, long = _drive(template)
    assert got["longShown"] >= max(_FLOORS[template], len(long) * 15), (
        f"{len(long)} chars leave at "
        f"{len(long) / (got['longShown'] / 60.0):.1f} chars/s"
    )
