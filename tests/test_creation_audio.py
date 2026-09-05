"""Every game rings, from one synthesised preamble, with nothing external.

The harsh review's first zero was silence. The fix follows the knowledge
base (docs/research/game-design-notes.md §1-2): retro SFX are an oscillator
plus a short envelope, buildable on Web Audio in-page, so the house rule -
one file, no fetches - holds. These tests pin the vocabulary shared between
preamble and templates, the mute toggle, and that sound never cost a page
its playability.
"""

from __future__ import annotations

import re

import pytest

from sidra_ai.creation.audio import PREAMBLE_NAMES, SFX_PREAMBLE
from sidra_ai.creation.games import TEMPLATES, generate_game, validate_game_html

_CALL = re.compile(r"sfx\('(\w+)'\)")


@pytest.mark.parametrize("key", sorted(TEMPLATES))
def test_every_template_rings_and_still_plays(key: str) -> None:
    game = generate_game(f"{key} のゲームを作って", template=key)

    assert "AudioContext" in game.html
    calls = _CALL.findall(game.html)
    assert len(calls) >= 2, f"{key} is effectively silent"
    verdict = validate_game_html(game.html)
    assert verdict["playable"], verdict["failures"]


@pytest.mark.parametrize("key", sorted(TEMPLATES))
def test_templates_only_ask_for_sounds_the_preamble_knows(key: str) -> None:
    """An unknown name is silence by design - but a *typo* should not ship."""

    calls = set(_CALL.findall(TEMPLATES[key].script))
    unknown = calls - set(PREAMBLE_NAMES)
    assert not unknown, f"{key} asks for sounds that do not exist: {unknown}"


def test_every_defined_sound_is_played_by_the_generated_page() -> None:
    """A sound nobody plays is vocabulary drift waiting to happen.

    Read off a built page rather than the template bodies alone: since
    C-1105 the losing sound belongs to the shared failure beat, so a
    template that plays it by hand would be the drift, not the proof.
    """

    used = set()
    for key in TEMPLATES:
        used |= set(_CALL.findall(generate_game("ゲームを作って", template=key).html))
    unused = set(PREAMBLE_NAMES) - used
    assert not unused, f"defined but never played: {unused}"


def test_the_preamble_is_self_contained_and_mutable() -> None:
    assert "MUTED" in SFX_PREAMBLE
    assert "http://" not in SFX_PREAMBLE and "https://" not in SFX_PREAMBLE
    for extension in (".mp3", ".wav", ".ogg"):
        assert extension not in SFX_PREAMBLE


def test_audio_failure_cannot_crash_the_game() -> None:
    """The sfx body is wrapped: no audio device is a machine, not a bug."""

    assert "try{" in SFX_PREAMBLE and "catch(err)" in SFX_PREAMBLE


def test_the_hit_is_noise_and_the_melody_is_a_tone() -> None:
    """§2's explosion family (C-1308), read off the page's own AudioContext.

    The hurt effect must be white noise through a falling low-pass, the gem
    must still be an oscillator, and the loudness contract must not move.
    """

    import json as _json
    import re as _re
    import shutil as _shutil
    import subprocess as _subprocess

    import pytest as _pytest

    from sidra_ai.creation.audio import PROBE
    from sidra_ai.creation.games import generate_game

    if _shutil.which("node") is None:  # pragma: no cover - environment guard
        _pytest.skip("node is required to drive the page")
    page = generate_game("シューティングゲームを作って").html
    script = _re.search(r"<script>(.*?)</script>", page, _re.S)
    assert script is not None
    probe = _subprocess.run(
        ["node", "-"],
        input=PROBE.replace("SCRIPT_PLACEHOLDER", script.group(1)),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    heard = _json.loads(probe.stdout.strip().splitlines()[-1])

    assert "noise->lowpass" in heard["hurtNodes"]
    assert "lowpass->out" in heard["hurtNodes"]
    assert "oscillator" not in heard["hurtNodes"]
    assert "noise->direct" not in heard["hurtNodes"]
    # A pulse voice since C-1350: still an oscillator, never noise, but
    # one that hands its own comb to the graph first.
    assert heard["gemNodes"] == ["pulse", "oscillator"]
    assert heard["mutedPlayed"] == 0
    assert heard["loud"] and heard["loud"] > heard["calm"]

    # §14 (C-1317): the same effect eight times over never lands on the
    # same pitch twice, stays well under a semitone of the table's value,
    # and the mute stops the variation with the sound.
    freqs = heard["catchFreqs"]
    assert len(freqs) == 8
    assert len(set(freqs)) >= 4, "the repeat is a machine again"
    assert all(500 * 0.92 <= f <= 500 * 1.08 for f in freqs), freqs
    assert heard["mutedFreqs"] == 0


def test_the_victory_is_a_rising_phrase_and_the_mute_still_wins() -> None:
    """§2 (C-1326): the heaviest beat gets the powerUp shape - a rising
    major arpeggio, every note on the gain books, silent under M."""

    import json as _json
    import re as _re
    import shutil as _shutil
    import subprocess as _subprocess

    import pytest as _pytest

    from sidra_ai.creation.audio import PROBE
    from sidra_ai.creation.games import generate_game

    if _shutil.which("node") is None:  # pragma: no cover - environment guard
        _pytest.skip("node is required to drive the page")
    page = generate_game("シューティングゲームを作って").html
    script = _re.search(r"<script>(.*?)</script>", page, _re.S)
    assert script is not None
    probe = _subprocess.run(
        ["node", "-"],
        input=PROBE.replace("SCRIPT_PLACEHOLDER", script.group(1)),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    heard = _json.loads(probe.stdout.strip().splitlines()[-1])

    freqs = heard["winFreqs"]
    assert len(freqs) >= 3, "a phrase, not a beep"
    assert all(freqs[i] < freqs[i + 1] for i in range(len(freqs) - 1))
    assert heard["winGains"] == len(freqs), "every note on the loudness books"
    assert heard["winMutedFreqs"] == 0
