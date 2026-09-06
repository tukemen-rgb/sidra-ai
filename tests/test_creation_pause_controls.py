"""The pause screen answers "what was the key again?" (C-1444).

The briefing table - objective, controls, threat - is news only once, so
from the second visit the page skips it and opens straight into play
(C-1111). That is right, and it left the controls written down nowhere a
player could reach: pause showed 「一時停止」 and how to resume, and
nothing else.

Driven on a RETURN visit throughout, because that is the case at issue.
A first visit still has its briefing, so a check that started there would
be testing the screen that was never the problem.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.startscreen import PREAMBLE_NAMES, pause_probe_source

LABELS = ("目標", "操作", "敵")


def _drive(template: str, *, returning: bool = True) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to press pause on a running page")
    page = generate_game("ゲームを作って", template=template).html
    body = re.search(r"<script>(.*?)</script>", page, re.S)
    assert body is not None
    store = {f"sidra.seen.{template}": "1"} if returning else {}
    ran = subprocess.run(
        ["node", "-"],
        input=pause_probe_source(body.group(1), store=store),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert ran.returncode == 0, ran.stderr[:400]
    return json.loads(ran.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_pause_shows_the_three_lines_and_resume_takes_them_away(template: str) -> None:
    seen = _drive(template)

    assert seen["skipped"], "the briefing was not skipped, so this is the wrong case"
    assert "一時停止" in seen["paused"]
    for label in LABELS:
        assert label in seen["paused"], f"{template}: {label}"
    # ...and the lines, not only the labels: a table of headings would
    # answer nothing.
    brief = seen["brief"]
    if brief and len(brief) == 3:
        for line in brief:
            assert any(line[:12] in drew for drew in seen["paused"]), line[:20]
    assert not any(label in seen["resumed"] for label in LABELS)


def test_the_pause_screen_adds_nothing_the_title_would_not_say() -> None:
    """Same three lines, from the same function - so the two screens
    cannot drift apart as templates change."""

    first = _drive("shooter", returning=False)
    again = _drive("shooter")

    brief = again["brief"]
    assert brief and len(brief) == 3
    for line in brief:
        assert any(line[:12] in drew for drew in first["atLoad"]), "title lost it"
        assert any(line[:12] in drew for drew in again["paused"]), "pause lost it"


def test_the_table_is_one_function_rather_than_two_copies() -> None:
    assert "gateBriefTable" in PREAMBLE_NAMES
    page = generate_game("ゲームを作って", template="shooter").html
    assert page.count("function gateBriefTable") == 1
    # ...and no template defines one of its own, which would break only in
    # the generated page.
    assert not any("function gateBriefTable(" in s.script for s in TEMPLATES.values())
