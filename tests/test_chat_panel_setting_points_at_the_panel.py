"""C-1861: the page's own dials are pointed at, not denied.

The generated page carries a tuning panel (volume, music, haptic,
reduce-motion). Asking for any of them got 「『動き』は増減できません」, or the list
of revisable parameters, or - for 「振動を切って」 - the instruction to ingest a
repository. The panel was there the whole time; only the sentence was missing.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.revise import asks_about_panel, panel_setting_labels
from sidra_ai.creation.tuning import VIEWER_SETTING_KEYS
from sidra_ai.evals.chat_panel_setting_points_at_the_panel import (
    NOT_PANEL,
    PANEL_REQUESTS,
    evaluate_chat_panel_setting_points_at_the_panel,
)


def test_panel_setting_eval_passes():
    result = evaluate_chat_panel_setting_points_at_the_panel()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 17


@pytest.mark.parametrize("request_text", PANEL_REQUESTS)
def test_a_dial_is_recognised(request_text):
    assert asks_about_panel(request_text)


@pytest.mark.parametrize("request_text", sorted(NOT_PANEL))
def test_the_neighbours_are_not_dials(request_text):
    """「音を消して」 is a feature request (C-1814) and 「消して」 a deletion."""

    assert not asks_about_panel(request_text)


def test_the_word_that_comes_back_is_one_someone_typed():
    """Matching is folded; the answer quotes this, so it must not be.

    Measured while writing the rule: the folded form came back as 「動キ」 and
    would have been quoted at the reader.
    """

    assert asks_about_panel("さっきのゲームの動きを減らして") == "動き"
    assert asks_about_panel("さっきのゲームの揺れを弱くして") == "揺れ"


def test_a_dial_is_not_the_thing_the_dial_controls():
    """「BGMを変えて」 asks for another tune; the panel only sets its volume.

    Caught by C-1802's check while this rule was being written - the first
    vocabulary carried bare 「音楽」 and 「BGM」, and pointing someone at the
    panel for those would trade this item's false 「no」 for a false 「yes」.
    """

    assert not asks_about_panel("それのBGMを変えて")
    assert not asks_about_panel("さっきのゲームの音楽を変えて")
    assert asks_about_panel("さっきのゲームのBGMの音量を下げて") == "音量"


def test_the_offer_is_read_off_the_real_panel():
    """Every viewer dial the schema carries, in the schema's own words."""

    labels = panel_setting_labels("adventure", "normal")
    assert len(labels) == len(VIEWER_SETTING_KEYS)
    assert "動きを減らす" in labels
    assert "振動" in labels
    # A template with no ladder cannot be described, and says nothing rather
    # than inventing a panel.
    assert panel_setting_labels("not-a-template", "normal") == ()
