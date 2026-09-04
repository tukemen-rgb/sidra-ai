"""C-1128: an empty frame must not be announced as a finished thing.

The generators were already honest about the *artifact* - blanks are
labelled 〔社長が埋める欄〕 and counted - and dishonest about the *sentence*
beside it. 「「進捗報告」を 4 枚で作りました」 is what you say when four
slides exist; four blank slides are one frame. These tests hold both ends:
the notice appears when nothing could be filled, and disappears the moment
one section can be.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.deck_job import build_deck_generator
from sidra_ai.creation.document_job import build_document_generator
from sidra_ai.creation.documents import BLANK, CONTENT_SECTIONS, SECTIONS
from sidra_ai.creation.empty import (
    EMPTY_HEADLINE,
    EMPTY_INDEX,
    EMPTY_KEPT,
    EMPTY_UNMATCHED,
    empty_notice,
)
from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.intent import detect_creation_intent

DECK_ASK = "進捗をまとめたデッキを作って"
DOC_ASK = "進捗レポートを作って"

#: Lands under a section of the status outline.
FITS = Fact(text="いま出来ることは索引の全文検索です。", source="README.md")
#: Matches no section cue and carries no number, so every slide stays blank
#: even though evidence did arrive - the case that makes the cause worth
#: reporting rather than assuming.
STRAY = Fact(text="ジャムの煮沸はよく混ぜる。", source="jam.md")


@pytest.fixture()
def decks(tmp_path):
    make = build_deck_generator(tmp_path)
    return lambda facts: make(DECK_ASK, detect_creation_intent(DECK_ASK), facts)


@pytest.fixture()
def documents(tmp_path):
    make = build_document_generator(tmp_path)
    return lambda facts: make(DOC_ASK, detect_creation_intent(DOC_ASK), facts)


def test_notice_is_silent_until_every_content_section_is_blank():
    assert empty_notice(blank=0, total=4, facts_available=0) == ""
    assert empty_notice(blank=3, total=4, facts_available=0) == ""
    assert empty_notice(blank=4, total=4, facts_available=0).startswith(EMPTY_HEADLINE)


def test_notice_never_fires_on_a_shape_with_no_sections():
    # A generator that reports nothing at all is not thereby empty; the
    # guard keeps a future caller from scoring a bug as honesty.
    assert empty_notice(blank=0, total=0, facts_available=0) == ""


def test_notice_names_the_cause_that_happened():
    nothing = empty_notice(blank=2, total=2, facts_available=0)
    unmatched = empty_notice(blank=2, total=2, facts_available=5)
    assert EMPTY_INDEX in nothing
    assert EMPTY_INDEX not in unmatched
    assert EMPTY_UNMATCHED.format(n=5) in unmatched
    assert "5 件" in unmatched


def test_empty_deck_is_not_called_a_deck(decks):
    outcome = decks([])
    assert EMPTY_HEADLINE in outcome.summary
    assert EMPTY_INDEX in outcome.summary
    assert "作りました" not in outcome.summary
    assert outcome.details["empty"] is True


def test_the_notice_comes_first(decks, documents):
    # Position is the point. A summary that announces a deck and mentions
    # the trouble at the end is the sentence this was filed about; an owner
    # reads the first clause and stops.
    for outcome in (decks([]), documents([])):
        assert outcome.summary.startswith(EMPTY_HEADLINE)


def test_empty_deck_still_leaves_the_frame_on_disk(decks):
    outcome = decks([])
    assert outcome.artifact_path
    assert EMPTY_KEPT in outcome.summary


def test_a_deck_with_one_filled_section_is_announced_as_before(decks):
    outcome = decks([FITS])
    assert EMPTY_HEADLINE not in outcome.summary
    assert "枚で作りました" in outcome.summary
    assert outcome.details["empty"] is False


def test_evidence_that_fits_nowhere_is_not_reported_as_an_empty_index(decks):
    outcome = decks([STRAY])
    assert outcome.details["empty"] is True, "the stray fact filled a slide"
    assert EMPTY_HEADLINE in outcome.summary
    assert EMPTY_INDEX not in outcome.summary
    assert "1 件" in outcome.summary


def test_empty_document_is_not_called_a_report(documents):
    outcome = documents([])
    assert EMPTY_HEADLINE in outcome.summary
    assert EMPTY_INDEX in outcome.summary
    assert "作りました" not in outcome.summary
    assert outcome.details["empty"] is True
    assert outcome.artifact_path


def test_a_document_with_evidence_is_announced_as_before(documents):
    outcome = documents([Fact(text="進捗は 3 件です。", source="PR-1.md")])
    assert EMPTY_HEADLINE not in outcome.summary
    assert "レポートを作りました" in outcome.summary
    assert outcome.details["empty"] is False


def test_the_always_blank_section_is_not_counted_as_content():
    # 「まだ埋まっていないこと」 is written blank in every report there has
    # ever been. Counting it would make a full report read as empty, which
    # is the same lie pointing the other way.
    assert "まだ埋まっていないこと" in SECTIONS
    assert "まだ埋まっていないこと" not in CONTENT_SECTIONS
    assert "出典" not in CONTENT_SECTIONS
    assert set(CONTENT_SECTIONS) < set(SECTIONS)


def test_a_filled_report_still_carries_its_blank_section(documents):
    # The evidence for the test above, from the product rather than the
    # constant: a report with content in it keeps one blank on purpose.
    outcome = documents([Fact(text="進捗は 3 件です。", source="PR-1.md")])
    assert outcome.details["unfilled"] == ["まだ埋まっていないこと"]
    assert BLANK in open(outcome.artifact_path, encoding="utf-8").read()
