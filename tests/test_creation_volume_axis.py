"""A dial for the sound, not just an off switch.

C-1408: the panel could change the difficulty, two axes, the accent and
three flags, and the only thing it could do about sound was M - all or
nothing. That is no answer for a game that is welcome but loud.

The rule worth testing is where the factor goes. The fight's loudness step
(§6 観察 4) is a *ratio* between two gains, so a volume multiplied in
before the ``MAX_GAIN`` clamp would be squeezed at full volume and not at
half, and the step would quietly depend on where the slider sits.
Multiplying after the ceiling leaves every ratio exactly as its author set
it and only makes the whole quieter.

Note what that costs to measure: nothing the product ships comes near the
ceiling (the loudest effect peaks at 0.48 against 0.9), so with the shipped
values the two orderings are indistinguishable in any real sound. The
ordering is therefore checked through ``musicNote``, which takes its gain
from the caller, at a value the clamp does bind. The inert ceiling itself
is filed as C-1410.
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

from sidra_ai.creation.audio import MAX_GAIN, volume_probe_source  # noqa: E402
from sidra_ai.creation.games import generate_game  # noqa: E402
from sidra_ai.creation.tuning import panel_schema  # noqa: E402
from sidra_ai.creation.games import _DIFFICULTY  # noqa: E402


def _listen(volume: int) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to hear the page")
    found = re.search(
        r"<script>(.*?)</script>", generate_game("シューティングゲームを作って").html, re.S
    )
    assert found is not None
    run = subprocess.run(
        ["node", "-"],
        input=volume_probe_source(found.group(1), volume=volume),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert run.returncode == 0, run.stderr.strip()[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_the_panel_carries_a_volume_axis() -> None:
    schema = panel_schema(
        "shooter", _DIFFICULTY["shooter"], difficulty="normal", accent="#ffffff"
    )
    field = next(f for f in schema["fields"] if f["key"] == "volume")

    assert field["default"] == 100, "a page must open at the loudness it was built with"
    assert (field["min"], field["max"]) == (0, 100)
    assert field["integer"] is True


def test_half_volume_halves_the_gain_the_page_schedules() -> None:
    full, half = _listen(100), _listen(50)

    assert full["calm"], "nothing was played at full volume"
    assert half["calm"] == pytest.approx(full["calm"] * 0.5)


def test_zero_is_silence_rather_than_a_very_quiet_sound() -> None:
    """Scheduling one would hand exponentialRampToValueAtTime a start of 0,
    which has no defined ramp, and would build a node graph nobody hears."""

    off = _listen(0)

    assert off["calm"] is None
    assert off["tuneCount"] == 0


def test_the_dial_and_the_mute_are_different_controls() -> None:
    half = _listen(50)

    assert half["mutedPlayed"] == 0, "M no longer silences the page"
    assert half["afterMute"] == half["calm"], "releasing M lost the set volume"


def test_the_setting_survives_the_trip_through_storage() -> None:
    for level in (100, 50, 0):
        assert _listen(level)["stored"] == level


def test_the_music_rides_the_same_dial() -> None:
    full, half = _listen(100), _listen(50)

    assert full["tune"]
    assert half["tune"] == pytest.approx(full["tune"] * 0.5)


def test_the_volume_does_not_change_the_fights_loudness_step() -> None:
    """The reason the factor goes after the ceiling rather than before."""

    full, half = _listen(100), _listen(50)

    assert full["calm"] and half["calm"]
    assert full["loud"] / full["calm"] == pytest.approx(half["loud"] / half["calm"])


def test_the_ordering_is_measured_where_the_ceiling_actually_binds() -> None:
    """With the shipped values it never does - see C-1410.

    ``musicNote`` takes its gain from the caller, so the probe asks it for
    one the clamp binds. Applied correctly the clamped gain still halves;
    applied before the clamp it would not.
    """

    full, half = _listen(100), _listen(50)

    assert full["clampedTune"] == pytest.approx(MAX_GAIN)
    assert half["clampedTune"] == pytest.approx(full["clampedTune"] * 0.5)
