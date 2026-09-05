"""The perfect throw pays double (§13 事実 1, C-1331).

The default template was the last one where a skilled press and a timid
press scored the same point. The middle of the band is now the 会心 zone,
drawn deeper so the bargain is visible; waiting for it risks the marker
leaving the band entirely, and the cautious edge press keeps its old 1.
Three real presses on the running page price the risk in both directions.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.fishing import precision_probe
from sidra_ai.creation.games import generate_game


def _thrown(request: str = "釣りゲームを作って") -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=precision_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("request_", ["釣りゲームを作って", "難しい釣りゲームを作って"])
def test_the_centre_pays_double_and_the_edge_pays_one(request_: str) -> None:
    thrown = _thrown(request_)

    assert thrown["perfect"] == {"gain": 2, "hits": 1, "crits": 1, "casts": 1}
    assert thrown["careful"] == {"gain": 1, "hits": 1, "crits": 0, "casts": 1}


def test_the_risk_is_real_in_both_directions() -> None:
    """Waiting for the centre can mean missing the band entirely."""

    thrown = _thrown()

    assert thrown["wide"] == {"gain": 0, "hits": 0, "crits": 0, "casts": 1}
    assert 0 < thrown["crit"] < 1, "the 会心 zone must be a strict slice of the band"


def test_points_and_fish_are_counted_apart() -> None:
    """C-1405's precedent: the number drawn and the number banked agree."""

    thrown = _thrown()

    assert thrown["score"] == 3, "2 for the centre + 1 for the edge"
    assert thrown["hits"] == 2 and thrown["crits"] == 1
