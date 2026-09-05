"""Duty ratio: the last sfxr parameter (§2, C-1350).

The synth had every axis of the 8-bit palette but one - waveform, ADSR,
frequency slide, vibrato, noise through a low-pass - and its three square
voices all played the same 50% width. A pulse voice hands its Fourier
series to createPeriodicWave, so the duty is read back off the spectrum's
comb: harmonic n weighs sin(n*pi*d)/n and the first null sits at n = 1/d.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.audio import PROBE
from sidra_ai.creation.games import generate_game


@pytest.fixture(scope="module")
def heard() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to listen to the page")
    page = generate_game("シューティングゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=PROBE.replace("SCRIPT_PLACEHOLDER", script.group(1)),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def _duty_of(imag: list[float]) -> int:
    """The comb's first null: harmonic n where sin(n*pi*d) vanishes."""

    null = next(
        (n for n in range(2, 32) if abs(imag[n]) < 1e-4 and abs(imag[n - 1]) > 1e-3),
        None,
    )
    assert null is not None, "the spectrum has no comb, so no duty to read"
    return null


@pytest.mark.parametrize(
    ("voice", "null"), [("sword", 4), ("gem", 8)], ids=["sword-25%", "gem-12.5%"]
)
def test_the_pulse_voice_plays_the_width_it_declares(heard, voice, null) -> None:
    waves = heard[f"{voice}Waves"]
    assert len(waves) == 1, "one effect, one custom wave"
    imag = waves[0]
    assert len(imag) == 32
    assert _duty_of(imag) == null
    # Every harmonic follows the pulse series, not just the null: a wave
    # with the right notch but the wrong body is some other instrument.
    for n in range(1, 32):
        assert abs(imag[n] - 2 / (n * math.pi) * math.sin(n * math.pi / null)) < 1e-4


def test_the_two_pulse_voices_are_different_instruments(heard) -> None:
    assert _duty_of(heard["swordWaves"][0]) != _duty_of(heard["gemWaves"][0])


def test_the_clash_keeps_its_square_name(heard) -> None:
    """50% duty IS the square: no custom wave, the plain oscillator."""

    assert heard["clashWaves"] == 0
    assert heard["clashNodes"] == ["oscillator"]


def test_the_mute_stops_the_pulse_voice_too(heard) -> None:
    assert heard["swordMutedWaves"] == 0
