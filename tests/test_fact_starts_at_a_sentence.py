"""C-1534: a report fact begins where a sentence begins.

Measured over the five indexed repositories on 2026-09-14: of the 11 bullets
under 「わかっていること」 in four generated reports, 3 started at the head of a
sentence. The other eight opened with 「…」 - and 19 of the 20 excerpt windows
those reports were built from already opened at a sentence end, a heading, a
list item, a table row or a paragraph break. The windows were fine; the mark
was not, because it was written whenever the window was not the head of the
chunk, which is a fact about the chunk and not about the sentence.

These pin the rule at the seam ``whole_sentences`` already owns, the narrow
branch the eval cannot see, and the surface that must not change.
"""

from __future__ import annotations

import pytest

from sidra_ai.api.citations import (
    _MAX_CANDIDATES,
    _MIN_ADVANCED,
    citation_excerpt,
    opens_cleanly,
    select_excerpt_span,
)
from sidra_ai.evals.fact_starts_at_a_sentence import (
    evaluate_fact_starts_at_a_sentence,
)
from sidra_ai.security.output_guard import OutputGuard

_ELLIPSIS = "…"


@pytest.fixture
def guard() -> OutputGuard:
    return OutputGuard()


@pytest.mark.parametrize(
    "content, start",
    [
        ("前の文です。次の文です。", 6),          # after a 。 mid-line
        ("前の行です\n| 区分 | 値 |\n", 6),       # a table row
        ("前の行です\n3. 三番目の項目\n", 6),      # an ordered item
        ("前の行です\n## 見出し\n", 6),           # a heading
        ("前の行です\n- 箇条書き\n", 6),          # a bullet
        ("狙い:\n\n新しい段落です。", 5),          # a paragraph break
        ("A sentence ends. Another begins.", 16),  # an ASCII sentence end
    ],
)
def test_these_are_places_a_reader_would_begin(content: str, start: int) -> None:
    assert opens_cleanly(content, start)


def test_a_wrapped_line_is_the_middle_of_a_sentence() -> None:
    # The one shape that is genuinely broken: this corpus hard-wraps Japanese
    # prose, so the newline is a wrap point, not a boundary.
    content = "この行は前の行の続きで\nあって、ここが後ろ半分です。"
    assert not opens_cleanly(content, content.index("あって"))


def test_the_chunks_own_head_is_never_broken() -> None:
    assert opens_cleanly("途中から始まる文です。", 0)


def test_a_clean_head_is_not_marked_but_the_clipped_tail_still_is(guard) -> None:
    content = (
        "冒頭の無関係な文がここに置かれています。" * 4
        + "\n| 区分 | 内容 |\n| セキュリティ規約 | ペンギンの飼育は許可制 |\n"
        + "後続の説明がここから続きます。" * 12
    )
    excerpt, _ = citation_excerpt(content, guard, "セキュリティ規約", clean_head=True)
    assert not excerpt.startswith(_ELLIPSIS)
    assert excerpt.endswith(_ELLIPSIS)


def test_a_real_mid_sentence_head_keeps_saying_so(guard) -> None:
    content = (
        "前置きの段落です。" * 8
        + "\nこの行は前の行の続きで\n"
        + "あって、ペンギンの飼育について述べている。次の文はここから始まる。\n"
        + "後続の段落が続きます。" * 12
    )
    excerpt, _ = citation_excerpt(content, guard, "ペンギン", clean_head=True)
    assert excerpt.startswith(_ELLIPSIS)
    # ...and the evidence is still there. A tidy head bought by dropping the
    # term the chunk was retrieved for is not an improvement.
    assert "ペンギン" in excerpt


def test_the_chat_citation_surface_is_unchanged(guard) -> None:
    # C-1264's mark tells an operator they are looking at a slice. The default
    # path must keep it even where the window opens on a clean line.
    content = (
        "冒頭の無関係な行です。" * 3
        + "\n"
        + "\n".join(f"段落{i}: 一般的な説明が続きます。" * 2 for i in range(1, 12))
        + "\nペンギンの飼育方法についてここで詳しく述べます。" * 3
        + "\n"
        + "\n".join(f"末尾{i}: さらに説明が続きます。" * 2 for i in range(1, 12))
    )
    default, _ = citation_excerpt(content, guard, "ペンギン")
    cleaned, _ = citation_excerpt(content, guard, "ペンギン", clean_head=True)
    assert default.startswith(_ELLIPSIS)
    assert not cleaned.startswith(_ELLIPSIS)


def _past_the_candidate_budget() -> str:
    """A chunk whose clean start lies beyond ``_MAX_CANDIDATES``.

    The advance fires only here: every clean start is also a candidate start,
    and selection already takes the latest window of equal score, so anywhere
    the budget reaches has been considered already. Packing the budget into a
    short prefix leaves the clean start invisible to selection and visible to
    the advance.
    """

    prefix = "あ。" * (_MAX_CANDIDATES - 2)
    return (
        prefix
        + "前の行の続きで\n"
        + "あって、ペンギンの話。ペンギンの飼育についてここで詳しく述べる。"
        + "後続。" * 40
    )


def test_the_advance_moves_a_mid_sentence_head_when_it_costs_no_evidence() -> None:
    content = _past_the_candidate_budget()
    plain, _ = select_excerpt_span(content, "ペンギン")
    advanced, window = select_excerpt_span(content, "ペンギン", clean_head=True)
    assert not opens_cleanly(content, plain)
    assert opens_cleanly(content, advanced)
    assert advanced > plain
    assert "ペンギン" in window


def test_the_advance_will_not_trade_the_window_away_for_a_tidy_head() -> None:
    # The only clean start ahead sits so near the end of the chunk that taking
    # it would leave less than ``_MIN_ADVANCED`` characters - a tidy head on an
    # excerpt that has stopped being evidence. It stays where it is, and the
    # 「…」 is what tells the reader.
    # The tail carries the query term, so the evidence guard would wave the
    # advance through; only the floor stops it. Keep them separable - a guard
    # that never decides anything is a guard that cannot be wrong.
    content = (
        "あ。" * (_MAX_CANDIDATES - 2)
        + "前の行の続きで\n"
        + "あって、ペンギンの話がずっと続きます、" * 4
        + "。ペンギンの話。"
    )
    assert len(content.split("。ペンギンの話。")[-1]) + len("ペンギンの話。") < _MIN_ADVANCED
    start, _ = select_excerpt_span(content, "ペンギン", clean_head=True)
    assert not opens_cleanly(content, start)
    excerpt, _ = citation_excerpt(content, OutputGuard(), "ペンギン", clean_head=True)
    assert excerpt.startswith(_ELLIPSIS)


def test_the_eval_passes() -> None:
    result = evaluate_fact_starts_at_a_sentence()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
