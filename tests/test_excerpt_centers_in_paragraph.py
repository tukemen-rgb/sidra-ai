"""C-1270: the citation window centres inside a Japanese paragraph.

select_excerpt_window (C-983) moved the excerpt to where the query is discussed,
but its candidate starts came only from newlines. Japanese prose ends sentences
with 。 and runs a paragraph on one line, so a chunk offered a single candidate -
the head - and the window could not reach an answer written past the cap.
Sentence boundaries are now candidate starts too.
"""

from __future__ import annotations

from sidra_ai.api.citations import select_excerpt_window
from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS
from sidra_ai.evals.excerpt_centers_in_paragraph import (
    evaluate_excerpt_centers_in_paragraph,
)

_FILLER = "前置きの段落がここに続く。"


def test_excerpt_centers_in_paragraph_eval_passes():
    result = evaluate_excerpt_centers_in_paragraph()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_window_reaches_an_answer_past_the_cap_with_no_newline():
    answer = "重要: バックアップは毎日午前 3 時に実行されます。"
    content = _FILLER * 40 + answer + "その後の説明。" * 20
    assert content.find("重要") > MAX_CITATION_EXCERPT_CHARS  # answer is past the cap
    assert "\n" not in content  # one paragraph, no line breaks

    window = select_excerpt_window(content, "バックアップの実行時刻はいつですか")
    assert "バックアップは毎日午前 3 時" in window
    assert len(window) <= MAX_CITATION_EXCERPT_CHARS


def test_window_opens_on_a_sentence_boundary_not_mid_sentence():
    answer = "重要: 連絡先は運用チームのオンコール窓口です。"
    content = _FILLER * 40 + answer + "その後の説明。" * 20
    window = select_excerpt_window(content, "連絡先を教えてください")
    start = content.index(window)
    # opens the chunk, a line, or a sentence - never the middle of one
    assert start == 0 or content[start - 1] in "\n。！？．"


def test_fallback_to_the_top_is_unchanged():
    content = _FILLER * 40 + "答えの一文。" + "その後。" * 20
    assert select_excerpt_window(content, "") == content[:MAX_CITATION_EXCERPT_CHARS]
    assert select_excerpt_window(content, "無関係 zzz") == content[:MAX_CITATION_EXCERPT_CHARS]
