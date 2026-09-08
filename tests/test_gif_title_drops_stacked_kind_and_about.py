"""C-1485: a GIF title peels stacked kind words and the about-phrase, not one.

The GIF follow-through to the document C-1467 (repeated peel) and C-1255 (about
-phrase). 「猫のGIFアニメを作って」 titled 「猫のGIF」 - the kind word GIF left in the
cover, doubling in the summary - and 「海に関するアニメGIFを作って」 kept 「に関する」.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.gifs import _title_from
from sidra_ai.evals.gif_title_drops_stacked_kind_and_about import (
    evaluate_gif_title_drops_stacked_kind_and_about,
)


def test_gif_title_stacked_eval_passes():
    result = evaluate_gif_title_drops_stacked_kind_and_about()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


@pytest.mark.parametrize(
    "request_text, expected",
    [
        ("猫のGIFアニメを作って", "猫"),
        ("猫のアニメーションGIFを作って", "猫"),
        ("海に関するアニメGIFを作って", "海"),
        ("猫についてのGIFを作って", "猫"),
        ("魚が泳ぐアニメについてのGIFを作って", "魚が泳ぐ"),
    ],
)
def test_stacked_kind_and_about_are_peeled(request_text, expected):
    assert _title_from(request_text) == expected


@pytest.mark.parametrize(
    "request_text, expected",
    [
        # a single kind word (already handled by C-1265), a subject that merely
        # begins with アニメ, and the bare-kind fallback title.
        ("猫のGIFを作って", "猫"),
        ("泳ぐ魚のアニメGIFを作って", "泳ぐ魚"),
        ("アニメ制作のGIFを作って", "アニメ制作"),
        ("光る星のアニメーションを作って", "光る星"),
        ("GIFを作って", "GIF"),
    ],
)
def test_existing_gif_titles_unchanged(request_text, expected):
    assert _title_from(request_text) == expected
