"""C-1839: an English 3D request is titled by its subject, not by its letters.

models3d._STRIP is built from optional groups, so it matched the empty string
everywhere and its \\s* removed every space: 「make a 3D model of a fish」 was
titled 'makeaofafish' and 'a fish' became 'afish'. Japanese has no spaces, so
only English broke - into a string no person wrote.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.models3d import _strip_kind_words, generate_model3d
from sidra_ai.evals.model3d_title_in_english import (
    JAPANESE,
    evaluate_model3d_title_in_english,
)


def test_model3d_english_title_eval_passes():
    result = evaluate_model3d_title_in_english()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


@pytest.mark.parametrize(
    ("request_text", "expected"),
    [
        ("make a 3D model of a fish", "fish"),
        ("make 3 3D models of a fish", "fish"),
        ("make a 3d model of a boat please", "boat"),
    ],
)
def test_an_english_request_is_titled_by_its_subject(request_text, expected):
    assert generate_model3d(request_text).title == expected


def test_an_empty_match_removes_nothing():
    # The smallest reproduction: no 3D, no model, and it lost its space.
    assert _strip_kind_words("a fish") == "a fish"
    assert _strip_kind_words("") == ""


@pytest.mark.parametrize(("request_text", "expected"), sorted(JAPANESE.items()))
def test_every_japanese_title_is_unchanged(request_text, expected):
    assert generate_model3d(request_text).title == expected


def test_an_english_request_naming_no_subject_takes_the_default():
    assert generate_model3d("make a model").title == "魚"
