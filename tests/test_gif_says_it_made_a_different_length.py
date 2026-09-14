"""C-1823: a GIF asked for in 30 frames says it made 10.

The asked-for number used to become the artifact's title while a different,
true number sat in the parenthesis of the same sentence; a length asked for
in seconds heard no number at all, because the summary counts frames.
length_note is the one source, both numbers derived (frames from the
validated bytes, seconds from DELAY_CS), silent when no length was asked for
and when the length asked for is the length made.
"""

from __future__ import annotations

from sidra_ai.creation.gif_job import build_gif_generator
from sidra_ai.creation.gifs import (
    DELAY_CS,
    FRAMES,
    length_note,
    loop_seconds,
    requested_frames,
    requested_seconds,
)
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.gif_says_it_made_a_different_length import (
    evaluate_gif_says_it_made_a_different_length,
)
from sidra_ai.evals.scratch import scratch_dir

_FRAMES_NOTE = "フレーム数は指定できません"
_SECONDS_NOTE = "長さは指定できません"


def _summary(request: str) -> str:
    gen = build_gif_generator(scratch_dir())
    return gen(request, detect_creation_intent(request)).summary or ""


def test_gif_length_eval_passes():
    result = evaluate_gif_says_it_made_a_different_length()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


def test_a_frame_count_that_was_not_built_is_disclosed():
    summary = _summary("30フレームのGIFを作って")
    assert _FRAMES_NOTE in summary
    assert f"{FRAMES} フレーム" in summary


def test_a_length_in_seconds_hears_the_real_loop():
    summary = _summary("5秒のGIFを作って")
    assert _SECONDS_NOTE in summary
    assert f"{loop_seconds(FRAMES):g} 秒" in summary


def test_a_request_with_no_length_adds_no_note():
    summary = _summary("魚のGIFを作って")
    assert _FRAMES_NOTE not in summary and _SECONDS_NOTE not in summary


def test_the_length_actually_made_adds_no_note():
    summary = _summary(f"{FRAMES}フレームのGIFを作って")
    assert _FRAMES_NOTE not in summary


def test_the_note_coexists_with_the_motif_and_colour_disclosures():
    summary = _summary("青い5秒のGIFを作って")
    assert _SECONDS_NOTE in summary
    assert "依頼に合う絵柄が無かったので" in summary
    assert "依頼にあった色は今の配色に反映していません" in summary


def test_both_numbers_are_derived_not_written_down():
    note = length_note("30フレームのGIFを作って", 7)
    assert "7 フレーム" in note
    seconds = length_note("5秒のGIFを作って", 5)
    assert f"{5 * DELAY_CS / 100:g} 秒" in seconds


def test_a_number_that_is_not_a_length_is_not_a_request():
    assert requested_frames("2026年のGIFを作って") is None
    assert requested_seconds("2026年のGIFを作って") is None
    assert requested_frames("30コマのGIFを作って") == 30
    assert requested_seconds("5秒間のGIFを作って") == 5
