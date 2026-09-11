"""The scroll guard decides; it is not merely spelled (§12, C-1671).

C-1215 fixed a real fault - arrows scrolled the board 208px off screen in
six presses - and ``evals/keys_dont_scroll.py`` then pinned it by looking
for three literal substrings in the generated HTML, never starting node.
Its docstring says the end-to-end proof "ran in a real browser at fix
time", which is the same sentence C-1666 found in ``touch_targets.py``,
where the pinned number turned out to be 18% wrong.

Scrolling needs a browser. The *decision* does not: the page's own
listeners are called here with a synthetic event and what is read back is
whether ``preventDefault()`` was reached.

Three directions, because a guard that prevents everything is as broken as
one that prevents nothing, and a guard that ignores form controls takes
the tuning panel's own switches with it - a checkbox is toggled with
Space.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game, scrollguard_probe

TEMPLATES = {
    "adventure": "冒険ゲームを作って",
    "duel": "ビームで撃ち合うゲームを作って",
    "marble": "玉転がしゲームを作って",
    "puzzle": "パズルゲームを作って",
    "fishing": "釣りゲームを作って",
}


def _asked(request: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=scrollguard_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_the_games_own_keys_are_kept_from_scrolling(name) -> None:
    seen = _asked(TEMPLATES[name])

    assert seen["listeners"], "the page registered no keydown listener at all"
    missed = [k for k, v in seen["board"].items() if not v]
    assert missed == [], missed


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_a_key_the_game_does_not_steer_with_is_left_alone(name) -> None:
    """Preventing everything would take the browser's own shortcuts too."""

    seen = _asked(TEMPLATES[name])

    assert not seen["innocent"], seen


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_focus_in_the_tuning_panel_keeps_its_keys(name) -> None:
    """The shared guard spared form controls from the start; each template's
    own preventDefault did not, so Space on a focused checkbox was
    swallowed by the game - including the panel's own switches."""

    seen = _asked(TEMPLATES[name])
    leaks = {
        tag: v for tag, v in seen["inForm"].items() if v["arrows"] or v["space"]
    }

    assert leaks == {}, leaks
