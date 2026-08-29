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


def test_every_defined_sound_is_used_by_some_template() -> None:
    """A sound nobody plays is vocabulary drift waiting to happen."""

    used = set()
    for spec in TEMPLATES.values():
        used |= set(_CALL.findall(spec.script))
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
