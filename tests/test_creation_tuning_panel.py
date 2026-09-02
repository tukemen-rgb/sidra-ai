"""The generated page can be fixed by hand, without asking again.

§9 学び (4) of the knowledge base: every generator on the market loses the
person at the same moment - the artifact is nearly right, and the only
offers on the table are "ask again and get something different" or "give
up". C-1112 answered half of that (a request edits the recorded parameters
and rebuilds). C-1113 is the half that needs nobody: the artifact ships its
own form.

Everything about *whether it works* is read off the running page. A page
that contains ``<input type=range>`` and a page whose slider changes the
game are different facts, and only the second is worth asserting - the same
distinction that made C-1018's pond ship as dead code. The Python-side
tests here cover only what the page cannot show: that the envelope is the
author's own difficulty span, and that a template cannot silently collide
with a name the preamble introduces.
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
    validate_game_html,
)
from sidra_ai.creation.tuning import (  # noqa: E402
    AXIS_LABELS,
    PREAMBLE_NAMES,
    SPEED_BINDING,
    TUNE_PREAMBLE,
    panel_schema,
    probe_source,
)

KEYS = sorted(TEMPLATES)


def _script(template: str) -> str:
    page = generate_game("ゲームを作って", template=template).html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None
    return found.group(1)


def _drive(template: str, *, stored: dict | None = None, target: float | None = None) -> dict:
    """Build the page, run its own panel in node, report what happened."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page's own panel")
    speeds = [pair[0] for pair in _DIFFICULTY[template].values()]
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(
            _script(template),
            stored={f"sidra.tune.{template}": stored} if stored else {},
            target=min(speeds) if target is None else target,
            speed_expr=SPEED_BINDING[template],
        ),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


# --------------------------------------------------------- the page itself


@pytest.mark.parametrize("template", KEYS)
def test_every_template_ships_the_panel(template: str) -> None:
    """One preamble, so a template written tomorrow is adjustable too."""

    seen = _drive(template)

    assert seen["panel"] is True
    assert seen["controls"] == ["difficulty", "speed", "band", "accent"]
    assert seen["buttons"] >= 1, "no way back to the defaults"


@pytest.mark.parametrize("template", KEYS)
def test_a_remembered_number_reaches_the_game(template: str) -> None:
    """The direction that matters: storage has to change the *game*.

    Read back through the template's own binding for ``SPEED_TOKEN``, not
    through the panel's readout - a panel that agreed with itself and left
    the game alone would pass any weaker check.
    """

    hardest = max(pair[0] for pair in _DIFFICULTY[template].values())
    default = _DIFFICULTY[template]["normal"][0]
    assert hardest != default, "this template's hard and normal speeds are equal"

    seen = _drive(template, stored={"speed": hardest})

    assert seen["speedSeen"] == hardest


@pytest.mark.parametrize("template", KEYS)
def test_moving_a_slider_saves_and_re_runs(template: str) -> None:
    easiest = min(pair[0] for pair in _DIFFICULTY[template].values())

    seen = _drive(template, target=easiest)

    assert seen["moved"] == easiest
    assert seen["reloads"] >= 1, "a change never asked the page to re-run"


@pytest.mark.parametrize("template", KEYS)
def test_the_defaults_can_be_got_back(template: str) -> None:
    """An adjustment nobody can undo is a worse trap than no adjustment."""

    seen = _drive(template, stored={"speed": max(p[0] for p in _DIFFICULTY[template].values())})

    assert seen["cleared"] is True
    assert seen["stored"] == []


@pytest.mark.parametrize("template", KEYS)
def test_a_junk_value_leaves_the_game_playable(template: str) -> None:
    """Storage is attacker-adjacent: it is whatever the last page wrote.

    A number far outside the author's range, a string where a number
    belongs, and a colour that is really a URL all have to land on the
    values the generator chose.
    """

    seen = _drive(
        template,
        stored={"speed": 10**6, "band": "nonsense", "accent": "javascript:alert(1)"},
    )
    designed = _DIFFICULTY[template]["normal"]
    hardest = max(pair[0] for pair in _DIFFICULTY[template].values())

    assert seen["speedSeen"] == hardest, "a huge value was not clamped to the author's span"
    assert seen["values"]["band"] == designed[1]
    assert seen["accentSeen"].startswith("#")


@pytest.mark.parametrize("template", KEYS)
def test_the_page_is_still_playable(template: str) -> None:
    verdict = validate_game_html(generate_game("ゲームを作って", template=template).html)

    assert verdict["playable"], verdict["failures"]


# ------------------------------------------------- what the page cannot say


@pytest.mark.parametrize("template", KEYS)
def test_the_envelope_is_the_authors_own_span(template: str) -> None:
    ladder = _DIFFICULTY[template]
    schema = panel_schema(template, ladder, difficulty="normal", accent="#123456")
    fields = {f["key"]: f for f in schema["fields"]}

    for key, index in (("speed", 0), ("band", 1)):
        values = [pair[index] for pair in ladder.values()]
        assert fields[key]["min"] == min(values)
        assert fields[key]["max"] == max(values)


@pytest.mark.parametrize("template", KEYS)
def test_a_whole_number_axis_keeps_whole_numbers(template: str) -> None:
    """``t % FALL`` and a board width are counts; a half is nonsense."""

    ladder = _DIFFICULTY[template]
    schema = panel_schema(template, ladder, difficulty="normal", accent="#123456")
    fields = {f["key"]: f for f in schema["fields"]}

    for key, index in (("speed", 0), ("band", 1)):
        values = [pair[index] for pair in ladder.values()]
        if all(float(v).is_integer() for v in values):
            assert fields[key]["integer"] is True
            assert fields[key]["step"] == 1


@pytest.mark.parametrize("template", KEYS)
def test_the_preset_is_the_same_table_the_generator_used(template: str) -> None:
    """One difficulty ladder, so the preset and the sliders cannot disagree."""

    ladder = _DIFFICULTY[template]
    schema = panel_schema(template, ladder, difficulty="hard", accent="#123456")
    field = next(f for f in schema["fields"] if f["key"] == "difficulty")

    assert field["default"] == "hard"
    assert field["presets"] == {
        name: {"speed": pair[0], "band": pair[1]} for name, pair in ladder.items()
    }


@pytest.mark.parametrize("template", KEYS)
def test_the_axis_is_labelled_with_what_it_does(template: str) -> None:
    """A slider called "speed" on the puzzle board would be a lie.

    The token contract is uniform; the meaning is not - ``SPEED_TOKEN`` is
    a fall speed in one template and a colour count in another.
    """

    assert template in AXIS_LABELS
    labels = {
        f["key"]: f["label"]
        for f in panel_schema(
            template, _DIFFICULTY[template], difficulty="normal", accent="#123456"
        )["fields"]
    }

    assert (labels["speed"], labels["band"]) == AXIS_LABELS[template]


@pytest.mark.parametrize("template", KEYS)
def test_no_template_shadows_a_panel_name(template: str) -> None:
    """A collision would break only in the generated page."""

    body = TEMPLATES[template].script
    for name in PREAMBLE_NAMES:
        assert f"function {name}(" not in body
        assert f"const {name}=" not in body
        assert f"let {name}=" not in body


def test_the_panel_never_leaves_the_machine() -> None:
    """The artifact's whole claim is that it is one local file.

    A panel that reported the settings somewhere would be a different
    product, so the absence is asserted rather than assumed.
    """

    for banned in ("fetch(", "XMLHttpRequest", "://", "sendBeacon", "WebSocket"):
        assert banned not in TUNE_PREAMBLE


@pytest.mark.parametrize("template", KEYS)
def test_the_accent_is_one_identifier_in_the_page(template: str) -> None:
    """One stored colour has to repaint every use, not the first one."""

    script = _script(template)

    assert "'CYAN_TOKEN'" not in script
    assert "TUNE_ACCENT" in script


def test_every_template_has_a_binding_the_judge_can_read() -> None:
    """The judge reads the game's own variable; a new template needs one."""

    assert set(SPEED_BINDING) >= set(TEMPLATES)
