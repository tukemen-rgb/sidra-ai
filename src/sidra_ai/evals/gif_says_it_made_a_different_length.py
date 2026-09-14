"""Does a GIF say it is not the length that was asked for?

C-1823. ``FRAMES`` and ``DELAY_CS`` are constants and there is no length to
set, so 「30フレームのGIFを作って」 answered

    「30フレーム」のアニメ GIF を作りました（絵柄: …・10 フレーム・…）

- the asked-for number became the artifact's name while a different, true
number sat in the parenthesis of the same sentence. 「5秒のGIFを作って」 was
worse: the real 0.8 second loop was stated nowhere, because the summary
reports frames and the request spoke of time.

The generator already admits the motif it could not draw (C-1258) and the
colour it could not use (C-1272); the length was the one left silent, the
same asymmetry the deck had about its slide count (C-1821). ``length_note``
is the one source of the admission, and both numbers in it are derived - the
frames from the validated bytes, the seconds from ``DELAY_CS``.

A request that named no length, and one whose length is the length made, add
no note. The checks drive the real ``build_gif_generator``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.gif_job import build_gif_generator
from sidra_ai.creation.gifs import (
    length_note,
    requested_frames,
    requested_seconds,
)
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.scratch import scratch_dir

#: The stable halves of the two sentences.
_FRAMES_NOTE = "フレーム数は指定できません"
_SECONDS_NOTE = "長さは指定できません"

#: C-1258 and C-1272, checked here only to prove all three coexist.
_MOTIF_NOTE = "依頼に合う絵柄が無かったので"
_COLOR_NOTE = "依頼にあった色は今の配色に反映していません"


@dataclass(frozen=True)
class GifLengthResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _summary(request: str) -> str:
    gen = build_gif_generator(scratch_dir())
    outcome = gen(request, detect_creation_intent(request))
    return getattr(outcome, "summary", "") or ""


def evaluate_gif_says_it_made_a_different_length() -> GifLengthResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    thirty = _summary("30フレームのGIFを作って")
    five_seconds = _summary("5秒のGIFを作って")
    fish_sixty = _summary("60フレームの魚のGIFを作って")
    ten = _summary("10フレームのGIFを作って")
    fish = _summary("魚のGIFを作って")
    blue_five = _summary("青い5秒のGIFを作って")

    # --- (A) a frame count that was not built is disclosed ----------------
    add(_FRAMES_NOTE in thirty and "10 フレーム" in thirty,
        "A: 「30フレーム」 is not told that ten frames were made")
    # --- (B) a length in seconds hears the real loop, in seconds ----------
    #     The summary's own numbers are all frames, so a reader who asked in
    #     time had no number to compare against at all.
    add(_SECONDS_NOTE in five_seconds and "0.8 秒" in five_seconds,
        "B: 「5秒」 is not told the loop is 0.8 seconds")
    # --- (C) a request with no length gets no note ------------------------
    add(_FRAMES_NOTE not in fish and _SECONDS_NOTE not in fish,
        "C: a bare 「魚のGIFを作って」 reports a length it was never asked for")
    # --- (D) the length actually made is not a substitution ---------------
    add(_FRAMES_NOTE not in ten and _SECONDS_NOTE not in ten,
        "D: 「10フレーム」 - the length actually made - wrongly gets a note")
    # --- (E) the request that had no disclosure at all now has one --------
    #     The motif exists (魚), so C-1258's note stays silent here; before
    #     this, that left the whole answer with nothing true about the length.
    add(_FRAMES_NOTE in fish_sixty and _MOTIF_NOTE not in fish_sixty,
        "E: 「60フレームの魚」 still carries no length disclosure")
    # --- (F) additive: the motif and colour notes still stand -------------
    add(_SECONDS_NOTE in blue_five
        and _MOTIF_NOTE in blue_five
        and _COLOR_NOTE in blue_five,
        "F: the length note replaced the motif or colour disclosure")
    # --- (G) both numbers are derived, not written down -------------------
    seven = length_note("30フレームのGIFを作って", 7)
    seven_seconds = length_note("5秒のGIFを作って", 5)
    add("7 フレーム" in seven and "0.4 秒" in seven_seconds,
        "G: the note does not report the frames actually written")
    # --- (H) a number that is not a length is not a request ---------------
    #     The unit word carries this: 「2026年のGIF」 has no digits in front of
    #     フレーム/コマ/秒, so it never matches.
    add(requested_frames("2026年のGIFを作って") is None
        and requested_seconds("2026年のGIFを作って") is None
        and requested_frames("30フレームのGIFを作って") == 30
        and requested_seconds("5秒のGIFを作って") == 5,
        "H: a year was read as a length, or a length was not read")

    return GifLengthResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = [
    "GifLengthResult",
    "evaluate_gif_says_it_made_a_different_length",
]
