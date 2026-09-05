"""C-1258: a GIF names its motif and says when it fell back to the default.

「猫のGIFを作って」 drew concentric rings (the default pulse) and the summary
named no motif and gave no sign the subject was not drawn. Now every summary
names the motif, an unnamed request says the default was used and names the
motif that can be asked for (魚), and a named motif (魚/釣り) stays silent. The
animation itself is unchanged.
"""

from __future__ import annotations

from sidra_ai.creation.gifs import (
    DEFAULT_MOTIF,
    generate_gif,
    named_motif,
    validate_gif,
)
from sidra_ai.evals.gif_motif_default_honest import (
    evaluate_gif_motif_default_honest,
)


def test_gif_motif_default_honest_eval_passes():
    result = evaluate_gif_motif_default_honest()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 13


def test_named_motif_distinguishes_default_from_explicit():
    assert named_motif("魚のGIFを作って") == "fish"
    assert named_motif("釣りのGIFを作って") == "fish"
    assert named_motif("猫のGIFを作って") is None
    assert named_motif("GIFを作って") is None


def test_generated_gif_records_whether_motif_was_named():
    assert generate_gif("魚のGIFを作って").motif_named is True
    assert generate_gif("猫のGIFを作って").motif_named is False
    # An explicit motif= is the caller naming it, even from a vague request.
    assert generate_gif("猫のGIFを作って", motif="fish").motif_named is True


def test_default_still_animates_and_is_the_named_default():
    gif = generate_gif("星のGIFを作って")
    assert gif.motif == DEFAULT_MOTIF
    assert gif.motif_named is False
    # The animation is a real, valid GIF - the note is about wording, not bytes.
    assert validate_gif(gif)["valid"] is True
