"""A generated deck may only contain figures somebody retrieved.

Every other property here - it renders, it has the right slides, it fetches
nothing - is table stakes. The one that matters is the last group: a deck is
dangerous exactly because it *looks* authoritative, so a figure on a slide
that appears in no evidence is the defect this file exists to catch, and the
mutation test proves the check can actually fail.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sidra_ai.creation.deck_job import build_deck_generator
from sidra_ai.creation.decks import (
    BLANK,
    Fact,
    GeneratedDeck,
    Slide,
    generate_deck,
    save_deck,
    save_pptx,
    validate_deck,
)
from sidra_ai.creation.intent import CreationKind, detect_creation_intent


@pytest.fixture
def facts() -> list[Fact]:
    return [
        Fact("課題: 索引した文書を人手で読み切れない", "owner/repo docs/BACKLOG.md"),
        Fact("解決: 引用付きで答える", "owner/repo docs/ARCHITECTURE.md"),
    ]


def test_a_deck_renders_with_a_slide_per_section(facts: list[Fact]) -> None:
    deck = generate_deck("営業用のデッキを作って", facts=facts)

    assert deck.outline == "pitch"
    assert len(deck.slides) == 4
    assert validate_deck(deck, facts)["usable"]


def test_sections_without_evidence_stay_blank(facts: list[Fact]) -> None:
    """The blank is the product. Filler here would read as fact."""

    deck = generate_deck("デッキを作って", facts=facts)

    unfilled = set(deck.unfilled)
    assert "根拠となる数字" in unfilled
    assert BLANK in deck.html
    # And the deck says so rather than only leaving a gap the reader may miss.
    assert "この欄は埋まっていません" in deck.html


def test_a_deck_with_no_evidence_at_all_is_still_honest() -> None:
    deck = generate_deck("デッキを作って")

    assert len(deck.unfilled) == len(deck.slides)
    assert validate_deck(deck, [])["usable"]


def test_a_figure_with_no_evidence_fails_validation(facts: list[Fact]) -> None:
    """The mutation that proves the check is load-bearing.

    Without this, `validate_deck` could be returning ``usable`` for every
    input and every other test here would still pass.
    """

    deck = generate_deck("デッキを作って", facts=facts)
    invented = Slide(title="課題", bullets=("売上は 500 万円です",), sources=("owner/repo",))
    mutated = GeneratedDeck(
        deck.outline, deck.title, (invented,) + deck.slides[1:], deck.html, deck.unfilled
    )

    verdict = validate_deck(mutated, facts)

    assert not verdict["usable"]
    assert any("not present in the evidence" in f for f in verdict["failures"])


def test_a_figure_that_was_retrieved_passes() -> None:
    """The other half: sourcing a number must not be impossible.

    A check that rejected every figure would also pass the test above, and
    would quietly make grounded decks unbuildable.
    """

    facts = [Fact("課題: 索引した文書が 1326 件ある", "owner/repo docs/OUTCOMES.md")]
    deck = generate_deck("デッキを作って", facts=facts)

    assert "1326" in deck.html
    assert validate_deck(deck, facts)["usable"]


def test_the_deck_fetches_nothing(facts: list[Fact]) -> None:
    """Same reason as the game page: loopback-bound machines."""

    deck = generate_deck("デッキを作って", facts=facts)

    assert "http://" not in deck.html
    assert "https://" not in deck.html
    assert "@import" not in deck.html


def test_the_request_chooses_the_outline() -> None:
    assert generate_deck("進捗報告のデッキを作って").outline == "status"
    assert generate_deck("提案デッキを作って").outline == "pitch"


def test_model_wording_cannot_reach_the_bullets(facts: list[Fact]) -> None:
    """A model may retitle a deck. It may not touch where numbers live."""

    deck = generate_deck("デッキを作って", facts=facts)
    retitled = deck.with_copy(title="新しい題")

    assert retitled.title == "新しい題"
    assert retitled.slides == deck.slides


def test_saving_writes_only_inside_the_data_dir(tmp_path: Path, facts: list[Fact]) -> None:
    deck = generate_deck("デッキを作って", facts=facts)

    path = save_deck(deck, tmp_path)

    assert path.parent == tmp_path / "artifacts"
    assert path.read_text(encoding="utf-8") == deck.html


def test_pptx_is_optional_and_says_which_it_was(tmp_path: Path, facts: list[Fact]) -> None:
    """Absence is reported, never silently swapped for the HTML file.

    Whichever way this container is configured, the pair (written, reason)
    has to describe what actually happened.
    """

    deck = generate_deck("デッキを作って", facts=facts)

    written, why = save_pptx(deck, tmp_path / "deck.pptx")

    assert why
    if written:
        assert (tmp_path / "deck.pptx").stat().st_size > 0
    else:
        assert "python-pptx" in why
        assert not (tmp_path / "deck.pptx").exists()


def test_the_generator_reports_what_it_left_blank(tmp_path: Path) -> None:
    """The summary an operator reads must name the gaps, not hide them.

    Driven with one fact, not none. C-1128 gave the *all* blank deck its own
    sentence - it is a frame, not a four-slide deck, and saying 「4 枚で
    作りました」 about it was the defect. This test is about the case that
    remains a deck: something landed, the rest did not, and the count of
    what did not has to be in the sentence rather than only in the file.
    """

    generate = build_deck_generator(tmp_path)
    ask = "デッキを作って"

    outcome = generate(
        ask,
        detect_creation_intent(ask),
        [Fact("課題: 索引した文書を読み切れない", "owner/repo docs/BACKLOG.md")],
    )

    assert outcome.handled
    assert outcome.kind is CreationKind.DECK
    assert "空欄" in outcome.summary
    assert Path(outcome.artifact_path).exists()
    assert outcome.details["unfilled"]
    assert outcome.details["empty"] is False


def test_evidence_reaches_the_slides_through_the_router(tmp_path: Path) -> None:
    """The wiring C-994 added: per-request facts, not just standing ones.

    Without this the deck renders honestly and entirely in blanks, which
    passes every other test in this file and is not what was asked for.
    """

    from sidra_ai.creation.router import build_default_router

    router = build_default_router(data_dir=str(tmp_path))
    intent = detect_creation_intent("デッキを作って")
    retrieved = [Fact("課題: 索引した文書を読み切れない", "owner/repo docs/BACKLOG.md")]

    without = router.route("デッキを作って", intent)
    with_evidence = router.route("デッキを作って", intent, retrieved)

    assert len(with_evidence.details["unfilled"]) < len(without.details["unfilled"])
    assert with_evidence.details["facts_available"] == 1


def test_a_section_with_no_matching_evidence_still_blanks(tmp_path: Path) -> None:
    """Evidence arriving is not permission to fill every slide.

    The cue tables exist to keep an unrelated passage out of a section, and
    this is the test that fails if a later edit makes matching greedy.
    """

    from sidra_ai.creation.router import build_default_router

    router = build_default_router(data_dir=str(tmp_path))
    unrelated = [Fact("天気の話をしています", "owner/repo docs/misc.md")]

    outcome = router.route("デッキを作って", detect_creation_intent("デッキを作って"), unrelated)

    assert len(outcome.details["unfilled"]) == outcome.details["slides"]


def test_a_numeric_section_takes_facts_that_carry_numbers() -> None:
    """"根拠となる数字" is filled by the presence of a figure, by construction.

    Which is also why the fabrication check keeps passing: the figure was in
    the evidence before it was on the slide.
    """

    facts = [Fact("索引した文書は 1326 件", "owner/repo docs/OUTCOMES.md")]
    deck = generate_deck("デッキを作って", facts=facts)

    assert "根拠となる数字" not in deck.unfilled
    assert validate_deck(deck, facts)["usable"]


def test_a_deck_that_fails_its_own_check_is_not_written(tmp_path: Path, monkeypatch) -> None:
    """A failed fabrication check must not produce a file.

    Writing it and reporting success would be the worst outcome available:
    an artifact on disk that a later reader has no reason to distrust.
    """

    from sidra_ai.creation import deck_job

    monkeypatch.setattr(
        deck_job, "validate_deck", lambda deck, facts: {"usable": False, "failures": ["probe"]}
    )
    generate = deck_job.build_deck_generator(tmp_path)

    outcome = generate("デッキを作って", detect_creation_intent("デッキを作って"))

    assert not outcome.handled
    assert not (tmp_path / "artifacts").exists()
