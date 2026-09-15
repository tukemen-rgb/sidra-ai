"""C-1850: every GIF motif can be asked for by name, and the offer says so.

The generator draws two motifs and only the fish had words. 「パルスのGIFを作って」
matched nothing, fell through to the default - the motif that had just been
named - and was announced with 「依頼に合う絵柄が無かった」 over an offer of 「魚」.

C-1258 (the sibling test next to this one) asserts the honest note appears when
no motif is named; this asserts the other half - that naming one is heard, and
that the offer is assembled from the catalogue rather than written out.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.gifs import (
    DEFAULT_MOTIF,
    MOTIF_LABELS,
    _MOTIF_WORDS,
    choose_motif,
    generate_gif,
    named_motif,
)
from sidra_ai.evals.gif_motif_named_is_heard import (
    NO_MOTIF_REQUESTS,
    PULSE_REQUESTS,
    evaluate_gif_motif_named_is_heard,
)


def test_gif_motif_named_eval_passes():
    result = evaluate_gif_motif_named_is_heard()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_every_motif_in_the_catalogue_has_words():
    """The catalogue and the vocabulary are the same length or one is stale."""

    assert set(_MOTIF_WORDS) == set(MOTIF_LABELS)
    assert all(_MOTIF_WORDS[key] for key in MOTIF_LABELS)


@pytest.mark.parametrize("request_text", PULSE_REQUESTS)
def test_naming_the_pulse_is_heard(request_text):
    assert named_motif(request_text) == "pulse"
    assert generate_gif(request_text).motif_named is True


@pytest.mark.parametrize("request_text", NO_MOTIF_REQUESTS)
def test_naming_no_motif_still_reports_the_default(request_text):
    assert named_motif(request_text) is None
    assert choose_motif(request_text) == DEFAULT_MOTIF
    assert generate_gif(request_text).motif_named is False


def test_a_subject_is_not_a_pattern():
    """The two near misses, kept apart on purpose.

    「波」 is a wave and 「山脈」 a mountain range - subjects this generator does
    not draw. Reading either as the concentric rings would trade one wrong
    sentence (「you named nothing」) for a worse one (「here is your wave」).
    """

    assert named_motif("波のGIFを作って") is None
    assert named_motif("山脈のGIFを作って") is None
    # ...while the pulse's own words are heard right next to them.
    assert named_motif("波紋のGIFを作って") == "pulse"
    assert named_motif("脈打つGIFを作って") == "pulse"


def test_the_fish_keeps_its_requests():
    assert named_motif("魚のGIFを作って") == "fish"
    assert named_motif("釣りのGIFを作って") == "fish"
    # Both named: the first match wins, which is what it did before C-1850.
    assert named_motif("魚が泳ぐ水槽のパルスGIFを作って") == "fish"
