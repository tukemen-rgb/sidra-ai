"""The break is quiet (§10 事実 4, C-1336).

Adaptive music's oldest rule is that the tune answers the state, and the
four bars were bouncing over 「ここまで」 and every end screen - painting
over the very silence the win and fail beats ring in. A duel left alone
loses on its own screen; the reservations are counted in three windows.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.music import end_probe


def _heard(request: str = "ビームで撃ち合うゲームを作って") -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=end_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(
    "request_",
    ["ビームで撃ち合うゲームを作って", "難しいビームで撃ち合うゲームを作って"],
)
def test_the_tune_runs_falls_silent_and_comes_back(request_: str) -> None:
    heard = _heard(request_)

    assert heard["endedBy"] == "template", "the duel must lose on its own screen"
    assert heard["during"] > 0, "the music never starts"
    assert heard["after"] == 0, "the loop plays over the break"
    assert heard["resumed"] > 0, "the music never comes back"
