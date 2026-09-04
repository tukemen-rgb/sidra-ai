"""The result screen leads back in instead of being a place to stop.

§8 事実 3: what turns one go into the next is knowing how far off you were
and being one tap from trying again. A screen that only says what happened
is a full stop.

Both halves stay on the machine. The personal best is this device's own
``localStorage`` - the same boundary the tuning panel and the index sit
inside - and the strip carries no URL and sends nothing.

Everything is read off the running page. The 「あと n」 branch is driven
twice on purpose: against an empty store (a first go is always a record)
and against a best nobody beat. A strip that only ever printed
自己ベスト更新 would pass the first run on its own.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.games import (  # noqa: E402
    TEMPLATES,
    _DIFFICULTY,
    generate_game,
)
from sidra_ai.creation.round import (  # noqa: E402
    PREAMBLE_NAMES,
    ROUND_SCORE,
    probe_source,
)

KEYS = sorted(TEMPLATES)


def _finish(template: str, *, best: int | None = None, hold: str | None = "ArrowRight") -> dict:
    """Play to the end of a round and read the result screen.

    A key is held for the whole go because since C-1123 that is what makes
    it a round somebody *played*: an abandoned page still runs to the end,
    but banks no best, no total and no streak, so the record checks below
    would otherwise be asking about a round nobody had.
    """

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to read the page's own result screen")
    page = generate_game("ゲームを作って", template=template).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    gentle = min(pair[0] for pair in _DIFFICULTY[template].values())
    source = probe_source(
        script.group(1),
        stored={f"sidra.tune.{template}": {"speed": gentle}},
        hold=hold,
    )
    if best is not None:
        source = source.replace(
            "const roundStore = {",
            'const roundStore = {"sidra.best.%s": "%d",' % (template, best),
            1,
        )
    probe = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=180
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("template", KEYS)
def test_the_round_ends_with_a_number(template: str) -> None:
    """"How far off am I" needs something to be off by."""

    seen = _finish(template)

    assert seen["score"] is not None
    assert isinstance(seen["score"], (int, float))


@pytest.mark.parametrize("template", KEYS)
def test_a_first_go_is_a_personal_best(template: str) -> None:
    seen = _finish(template)

    assert seen["record"] is True
    assert [line for line in seen["strip"] if "自己ベスト更新" in line], seen["strip"]


@pytest.mark.parametrize("template", KEYS)
def test_a_best_nobody_beat_shows_the_gap(template: str) -> None:
    """The other direction, and the one the item actually asks for."""

    seen = _finish(template, best=10**6)

    assert seen["record"] is False
    assert seen["best"] == 10**6
    said = [line for line in seen["strip"] if "自己ベスト" in line and "あと" in line]
    assert said, seen["strip"]


@pytest.mark.parametrize("template", KEYS)
def test_one_tap_from_the_result_starts_another_go(template: str) -> None:
    """§8's single tap - the thing a phone has and a keyboard shortcut is not."""

    tap = _finish(template, best=10**6)["afterTap"]

    assert (tap["live"] and not tap["ended"]) or tap["reloads"], tap


@pytest.mark.parametrize("template", KEYS)
def test_the_result_offers_a_way_back(template: str) -> None:
    seen = _finish(template, best=10**6)

    assert [line for line in seen["strip"] if "もう一度" in line], seen["strip"]


@pytest.mark.parametrize("template", KEYS)
def test_the_result_points_nowhere_outside(template: str) -> None:
    """Local completion: no URL on the screen and nothing sent."""

    seen = _finish(template, best=10**6)

    for line in seen["strip"]:
        assert "http" not in line and "://" not in line


# ------------------------------------------------- what the page cannot say


@pytest.mark.parametrize("template", KEYS)
def test_every_template_declares_what_it_counts(template: str) -> None:
    """No shared score variable exists, so each one is written down."""

    assert template in ROUND_SCORE
    expression, label = ROUND_SCORE[template]
    assert expression and expression != "null"
    assert label


@pytest.mark.parametrize("template", KEYS)
def test_no_template_shadows_the_result_names(template: str) -> None:
    body = TEMPLATES[template].script
    for name in PREAMBLE_NAMES:
        assert f"function {name}(" not in body
        assert f"const {name}=" not in body
        assert f"let {name}=" not in body


def test_the_best_lives_only_on_this_device() -> None:
    """A leaderboard would be a different product and a different promise."""

    from sidra_ai.creation.round import ROUND_PREAMBLE

    assert "sidra.best." in ROUND_PREAMBLE
    for banned in ("fetch(", "XMLHttpRequest", "://", "sendBeacon"):
        assert banned not in ROUND_PREAMBLE
