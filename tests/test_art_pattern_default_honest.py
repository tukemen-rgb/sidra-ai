"""C-1256: art tells the user when it fell back to the default pattern.

「螺旋のアートを作って」 named no pattern, silently became a flow field, and the
summary said only 「パターン: flow」. Now the summary adds an honest note that
the default was used and lists the two patterns; a request that named a pattern
(フロー/軌道/円…) stays silent, and the picture itself is unchanged.
"""

from __future__ import annotations

from sidra_ai.creation.art import (
    DEFAULT_PATTERN,
    generate_art,
    named_pattern,
)
from sidra_ai.evals.art_pattern_default_honest import (
    evaluate_art_pattern_default_honest,
)


def test_art_pattern_default_honest_eval_passes():
    result = evaluate_art_pattern_default_honest()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 11


def test_named_pattern_distinguishes_default_from_explicit():
    assert named_pattern("フローアートを作って") == "flow"
    assert named_pattern("軌道のアートを作って") == "orbits"
    assert named_pattern("円のアートを作って") == "orbits"
    # A request that names no pattern word returns None, not the default.
    assert named_pattern("螺旋のアートを作って") is None
    assert named_pattern("アートを作って") is None


def test_generated_art_records_whether_pattern_was_named():
    assert generate_art("螺旋のアートを作って").pattern_named is False
    assert generate_art("フローアートを作って").pattern_named is True
    assert generate_art("軌道のアートを作って").pattern_named is True
    # An explicit pattern= is the caller naming it, even from a vague request.
    assert generate_art("螺旋のアートを作って", pattern="orbits").pattern_named is True


def test_default_still_draws_and_is_the_named_default():
    art = generate_art("点描のアートを作って")
    assert art.pattern == DEFAULT_PATTERN
    assert art.pattern_named is False
    # The picture is a real, valid page - the note is about wording, not output.
    from sidra_ai.creation.art import validate_art

    assert validate_art(art)["valid"] is True
