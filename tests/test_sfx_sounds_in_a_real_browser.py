"""The synthesised voices, measured in a real browser (C-1974, §2).

The nine audio judges drive a hand-written ``AudioContext``. It accepts
whatever it is handed; a real browser does not. These tests keep the new
real-browser reading honest, and cover the nine templates the judge itself
does not open.
"""

from __future__ import annotations

import pathlib

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.evals.canvas_matches_the_language_asked import TEMPLATE_ASKS
from sidra_ai.evals.sfx_sounds_in_a_real_browser import (
    HELD_VOICES,
    _HOOK,
    _open,
    effect_names,
    evaluate_sfx_sounds_in_a_real_browser,
)
from sidra_ai.evals.targets_meet_the_size_floor import CHROME

#: The drawer as it stands. A new voice is welcome - it just has to be
#: added here too, so that nobody adds one the real browser never plays.
NAMES = (
    "sword", "cut", "gem", "key", "hurt", "graze", "fire", "charge",
    "clash", "catch", "powerup", "win", "lose", "step", "tick",
)


def test_the_table_is_read_from_the_page_itself() -> None:
    assert effect_names() == NAMES


def test_what_the_browser_refuses_is_recorded_and_re_thrown() -> None:
    """A probe that swallowed the refusal would make every page sound fine."""
    assert _HOOK.count("throw e") == 2, "both wrappers must re-throw"
    assert "__SFX.refused.push" in _HOOK


def test_the_judge_counts_the_held_voices_too() -> None:
    assert HELD_VOICES == ("engine", "music")


def test_every_template_sounds_in_a_real_browser() -> None:
    """The judge opens one page; the other nine are pinned here."""
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    wanted = set(effect_names()) | set(HELD_VOICES)
    silent: list[str] = []
    for key, ask in sorted(TEMPLATE_ASKS.items()):
        seen = _open(generate_game(ask).html)
        assert "err" not in seen, f"{key}: {seen.get('err')}"
        assert not seen.get("refused"), f"{key}: {seen.get('refused')}"
        silent += [f"{key}: {name}" for name in sorted(wanted - set(seen["sounded"]))]
    assert silent == [], silent


def test_the_judge_reads_a_real_context() -> None:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    result = evaluate_sfx_sounds_in_a_real_browser()
    assert result.voices_that_sound == result.voices_total, result.failures
    assert any("AudioContext" in line for line in result.readings), result.readings
