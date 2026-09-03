"""A score buys a colour, and never anything else.

§8 事実 6: somewhere for the time already spent to go is what brings
people back, and the usual way of building it is the way that ruins a
game - unlock the faster ship and everyone who arrives later is playing a
worse game than the people who arrived early.

So the interesting assertions here are not "an unlock exists". Each
template is played out twice by the same masher, on the same seed, with
the same inputs and the same cumulative total - once wearing the earned
skin and once not - and the two runs have to draw **the same shapes in
different colours**.

The behavioural check has a known blind spot, and it is written down
rather than papered over: a trace can only see an axis the masher
actually exercises, and the adventure keeps every enemy it has in a room
this player never reaches. That is why ``stray_calls`` exists and is
asserted separately - if nothing outside three call sites can reach a
skin, a skin cannot reach a number, whether or not a probe would have
noticed.
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
from sidra_ai.creation.skins import (  # noqa: E402
    PREAMBLE_NAMES,
    SANCTIONED_CALLS,
    SKIN_COLOURS,
    SKIN_PREAMBLE,
    SKIN_STEPS,
    SKIN_UNIT,
    probe_source,
    skin_spec,
    stray_calls,
)

KEYS = sorted(TEMPLATES)
#: One template is played end-to-end in every direction; running all nine
#: three times over is what the metric is for.
PLAYED = "shooter"


def _script(template: str) -> str:
    page = generate_game("ゲームを作って", template=template).html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None
    return found.group(1)


def _play(template: str, *, stored: dict | None = None, pick: str | None = None) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the page")
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(_script(template), stored=stored or {}, pick=pick),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


# ------------------------------------------------------- the fairness claim


def test_the_skin_changes_the_colours_and_nothing_else() -> None:
    """The whole item, in one comparison.

    Same seed, same inputs, same cumulative total - the *only* difference
    between the two runs is which colour is being worn.
    """

    earned = skin_spec(PLAYED)["skins"][1]
    total = {f"sidra.total.{PLAYED}": str(earned["at"])}

    plain = _play(PLAYED, stored=dict(total))
    worn = _play(PLAYED, stored={**total, f"sidra.skin.{PLAYED}": earned["id"]})

    assert plain["facts"]["current"] == "base"
    assert worn["facts"]["current"] == earned["id"]
    assert worn["geometry"] == plain["geometry"], "the skin changed what was drawn where"
    assert worn["scores"] == plain["scores"], "the skin changed how the round went"
    assert worn["colours"] != plain["colours"], "the skin changed nothing at all"
    assert earned["accent"].lower() in worn["colours"]
    assert earned["accent"].lower() not in plain["colours"]


@pytest.mark.parametrize("template", KEYS)
def test_nothing_outside_three_places_can_reach_a_skin(template: str) -> None:
    """The half of the claim a probe cannot make.

    A trace only sees an axis the masher exercises. This one holds for
    every template whether or not the run happened to touch it.
    """

    assert stray_calls(_script(template), template) == []


def test_the_sanctioned_calls_are_the_ones_the_page_makes() -> None:
    """A list nobody checks would drift into permission for anything."""

    script = _script(PLAYED)
    for call in SANCTIONED_CALLS:
        assert call in script


# --------------------------------------------------------- the unlock itself


def test_nothing_is_open_before_anything_is_played() -> None:
    seen = _play(PLAYED)

    assert seen["facts"]["unlocked"] == ["base"]
    assert [p["id"] for p in seen["pickers"] if p["locked"]] == [
        skin["id"] for skin in skin_spec(PLAYED)["skins"][1:]
    ]


def test_a_round_of_play_banks_into_the_total() -> None:
    seen = _play(PLAYED)

    assert seen["round"]["score"] is not None
    assert float(seen["storedTotal"]) == float(seen["round"]["score"])


@pytest.mark.parametrize("template", KEYS)
def test_the_first_colour_is_neither_free_nor_theoretical(template: str) -> None:
    """The measurement behind ``SKIN_UNIT``, replayed.

    The table says what one mashed-out round of each template scores, and
    the prices are multiples of it. Replaying it here is what stops a
    template whose scoring changes shape from leaving its prices behind -
    a colour the first round hands over is not a reason to play a second,
    and one a dozen rounds cannot reach is not a reason either.
    """

    seen = _play(template)
    scored = float(seen["storedTotal"])
    first = skin_spec(template)["skins"][1]["at"]

    assert scored > 0, "a round of play scored nothing at all"
    assert scored < first, f"one round opened a colour ({scored} >= {first})"
    assert first <= scored * 12, f"{first} is more than a dozen rounds of {scored}"


def test_pressing_an_earned_colour_applies_it() -> None:
    earned = skin_spec(PLAYED)["skins"][1]

    seen = _play(PLAYED, stored={f"sidra.total.{PLAYED}": str(earned["at"])}, pick=earned["id"])

    assert seen["picked"] == earned["id"]
    assert seen["reloads"] >= 1, "picking a colour never asked the page to re-run"


def test_a_locked_colour_cannot_be_worn() -> None:
    """Storage is whatever the last page wrote, so an unearned id is
    possible. It is only a colour - but a picker showing a skin as locked
    while the page wore it would be a lie."""

    seen = _play(PLAYED, stored={f"sidra.skin.{PLAYED}": "verdant"})

    assert seen["facts"]["current"] == "base"


def test_the_result_says_what_opened() -> None:
    """The reason to start the next round, said where the next round starts."""

    first = skin_spec(PLAYED)["skins"][1]
    seen = _play(PLAYED, stored={f"sidra.total.{PLAYED}": str(first["at"] - 1)})

    assert seen["facts"]["news"] == first["label"]
    assert [line for line in seen["said"] if first["label"] in line]


def test_the_result_stays_quiet_when_nothing_opened() -> None:
    seen = _play(PLAYED)

    assert seen["facts"]["news"] is None


# ------------------------------------------------- what the page cannot say


@pytest.mark.parametrize("template", KEYS)
def test_the_price_is_this_templates_own_score(template: str) -> None:
    """One shared threshold would price the puzzle and the adventure the
    same, and their rounds differ by two orders of magnitude."""

    spec = skin_spec(template)
    assert spec["unit"] == SKIN_UNIT[template] >= 1
    assert [skin["at"] for skin in spec["skins"]] == [0] + [
        SKIN_UNIT[template] * step for step in SKIN_STEPS
    ]


@pytest.mark.parametrize("template", KEYS)
def test_a_skin_has_nowhere_to_put_a_number(template: str) -> None:
    """A field that existed would eventually be used."""

    for skin in skin_spec(template)["skins"]:
        assert set(skin) == {"id", "label", "accent", "at"}
        assert skin["accent"] is None or re.fullmatch(r"#[0-9a-f]{6}", skin["accent"])


def test_the_free_colour_is_first_and_costs_nothing() -> None:
    assert SKIN_COLOURS[0][2] is None
    assert skin_spec(PLAYED)["skins"][0]["at"] == 0
    assert len(SKIN_COLOURS) == len(SKIN_STEPS) + 1


def test_the_total_never_leaves_the_machine() -> None:
    """The player's own record of their own play, kept where they made it."""

    for banned in ("fetch(", "XMLHttpRequest", "://", "sendBeacon", "WebSocket"):
        assert banned not in SKIN_PREAMBLE


@pytest.mark.parametrize("template", KEYS)
def test_no_template_shadows_a_skin_name(template: str) -> None:
    body = TEMPLATES[template].script
    for name in PREAMBLE_NAMES:
        assert f"function {name}(" not in body
        assert f"const {name}=" not in body
        assert f"let {name}=" not in body
