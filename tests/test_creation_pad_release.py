"""An interruption releases the pad too (§22×§4, C-1392).

focusRelease lifts the KEYS on blur/pagehide, but PAD_HELD was the pad's
own state: left alone it kept the held highlight lit on a button nobody
was touching, and a browser that recycles the pointerId handed the next
tap to padMove/padUp, which ate it. Now one real synthetic touch followed
by a blur with no pointerup empties the map, sends the keyup, and paints
the next frame's plate back in the declared colour.
"""

from __future__ import annotations

import json
import re
import subprocess

from sidra_ai.creation import generate_game
from sidra_ai.creation.touchpad import padhold_probe


def _drive() -> dict:
    html = generate_game("ゲームを作って", template="catch").html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=padhold_probe(script),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_the_touch_lands_and_lights_the_button() -> None:
    got = _drive()
    assert got["heldBefore"] == 1 and got["downSent"] == 1, (
        "the touch never landed on the pad"
    )
    assert got["heldPlateBefore"] == "held", "the held button never lights"


def test_the_blur_releases_the_map_the_key_and_the_highlight() -> None:
    got = _drive()
    assert got["heldAfter"] == 0, "the blur leaves the pad held"
    assert got["upSent"] == 1, "the release never sends the keyup"
    assert got["heldPlateAfter"] == "plate", "the highlight outlives the touch"
