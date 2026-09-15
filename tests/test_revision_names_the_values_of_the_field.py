"""C-1868: the refusal stops listing the field it is refusing.

「さっきのゲームの配色を変えて」 was answered 「何をどう変えるかが読み取れません
でした。いま変えられるのは 難易度・テーマ（配色）…」 - the answer printed in the
same sentence as the refusal. Five fields out of five behaved this way.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.revise import CHANGEABLE, field_values, names_a_field
from sidra_ai.creation.themes import THEMES
from sidra_ai.evals.revision_names_the_values_of_the_field import (
    FIELD_REQUESTS,
    NO_FIELD,
    evaluate_revision_names_the_values_of_the_field,
)


def test_field_values_eval_passes():
    result = evaluate_revision_names_the_values_of_the_field()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 20


@pytest.mark.parametrize("key,request_text", sorted(FIELD_REQUESTS.items()))
def test_naming_a_field_is_recognised(key, request_text):
    assert names_a_field(request_text) == key


@pytest.mark.parametrize("request_text", NO_FIELD)
def test_naming_no_field_is_not_a_field(request_text):
    assert names_a_field(request_text) == ""


def test_every_described_field_is_one_the_product_offers():
    """A sentence about a field nobody can set would be a new false promise."""

    offered = dict(CHANGEABLE)
    for key in FIELD_REQUESTS:
        assert key in offered, key
        assert field_values(key, "adventure")


def test_the_values_come_from_the_owning_tables():
    """Not written twice: a theme added upstream joins the sentence."""

    said = field_values("theme", "adventure")
    for name in THEMES:
        assert name in said
    # ...and the ladder is the template's own, not a constant.
    assert "easy" in field_values("difficulty", "adventure")
    assert field_values("difficulty", "not-a-template")
