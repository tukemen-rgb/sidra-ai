"""C-1215: game keys must not scroll the page out from under the game.

Six ArrowDown presses scrolled every generated page 208px - the board slid
off screen while the player walked south. One guard on the native listener
prevents the browser default for arrows and Space, except when focus is on
a form control, so the tuning panel's sliders keep their keys.
"""

from __future__ import annotations

import re

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.evals.keys_dont_scroll import evaluate_keys_dont_scroll


def test_guard_is_in_every_probed_template():
    result = evaluate_keys_dont_scroll()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5


def test_guard_excludes_form_controls():
    html = generate_game("冒険ゲームを作って").html
    assert "INPUT|TEXTAREA|SELECT|BUTTON" in html


def test_guard_registers_before_the_remap_wrapper():
    """The guard rides the native addEventListener (C-1305 wraps it later).

    Asked by driving the page rather than by comparing string offsets in
    the HTML (C-1671). The offsets were a proxy: naming the form-control
    test as a function and defining it above the registration moved the
    marker earlier and broke this, while the ordering it stands for was
    still exactly right. The property is "the guard is the first keydown
    listener", so that is what is asked - call only the first one.
    """

    import json
    import shutil
    import subprocess

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    from sidra_ai.creation.games import scrollguard_probe

    html = generate_game("冒険ゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", html, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=scrollguard_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    seen = json.loads(probe.stdout.strip().splitlines()[-1])

    assert seen["firstIsGuard"], seen
