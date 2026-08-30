"""The title screen says what the player is for, not only which keys exist.

§6 観察 3: the owner's episode opens its escalation on a briefing table, and
that scene is the reason the shooting afterwards reads as something going
wrong rather than as noise. A control list answers "what can I press"; it
does not answer "what am I trying to do".

The briefing is easy to fake in three ways, so all three are checked: a line
that never reaches the running page, a control line naming keys the template
does not read, and one boilerplate objective pasted across every template.
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

from sidra_ai.creation.games import TEMPLATES, generate_game  # noqa: E402
from sidra_ai.creation.startscreen import BRIEFINGS, probe_source  # noqa: E402
from sidra_ai.creation.story import CONTROLS  # noqa: E402


def _gate(template: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to read the running page")
    page = generate_game("ゲームを作って", template=template).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(script.group(1)),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout)


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_the_briefing_reaches_the_running_page(template) -> None:
    """A constant that never reaches the gate is still in the file."""

    brief = _gate(template)["brief"]

    assert isinstance(brief, list) and len(brief) == 3, template
    assert all(line.strip() for line in brief), template


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_the_briefing_does_not_start_the_game_early(template) -> None:
    """Three more lines to read is worth nothing if the game already began."""

    seen = _gate(template)

    assert seen["framesBeforePress"] == 0
    assert seen["stateAfter"] == "playing"
    assert seen["framesAfterPress"] > 0


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_the_control_line_names_a_key_the_template_reads(template) -> None:
    """Asked of the key table rather than copied from it: two tables drift."""

    keys = [key for key, _ in CONTROLS.get(template, ())]
    tokens = [t for key in keys for t in key.replace("/", " ").split() if t]
    line = BRIEFINGS[template][1]

    assert tokens, f"{template} has no control table to check against"
    assert any(token in line for token in tokens), (template, line, keys)


def test_no_two_templates_share_an_objective() -> None:
    """「敵を倒す」 over a fishing game is worse than no line at all."""

    objectives = [brief[0] for brief in BRIEFINGS.values()]

    assert len(set(objectives)) == len(objectives)


def test_every_template_has_a_briefing() -> None:
    assert set(BRIEFINGS) == set(TEMPLATES)


def test_a_template_without_a_briefing_falls_back_rather_than_breaking() -> None:
    """A missing entry must cost the framing, not the start screen."""

    page = generate_game("ゲームを作って", template="fishing").html

    assert "GBRIEF&&GBRIEF.length===3" in page, "the fallback branch is present"
    assert "gateWrap(GHOW,34)" in page, "the instruction line is what it falls back to"


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_the_three_labels_are_on_the_page(template) -> None:
    page = generate_game("ゲームを作って", template=template).html

    for label in ("目標", "操作", "敵"):
        assert label in page, (template, label)
