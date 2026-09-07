"""C-1475: the citation window reaches an answer at a paragraph's tail.

The tail twin of C-1270. `_candidate_starts` dropped every window start closer
to the end than `MAX_CITATION_EXCERPT_CHARS` (`last_useful_start`), so when the
answering sentence sat in a chunk's final ~200 characters - where conclusions
and values usually sit - no candidate window could open on it and the excerpt
clipped the answer at the far edge. Tail sentence boundaries are now candidate
starts too, while the top fallback and the C-1270 centring are unchanged.
"""

from __future__ import annotations

from sidra_ai.api.citations import select_excerpt_window
from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS
from sidra_ai.evals.excerpt_reaches_paragraph_tail import (
    _LEAD,
    evaluate_excerpt_reaches_paragraph_tail,
)

_FILLER = "前置きの段落がここに続く。"


def test_excerpt_reaches_paragraph_tail_eval_passes():
    result = evaluate_excerpt_reaches_paragraph_tail()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_window_reaches_an_answer_in_the_final_cap_of_the_chunk():
    answer = "API のレート制限は 1 分あたり 100 リクエストに設定されている。"
    content = "概要。" + _LEAD + answer
    # the answer sits inside the chunk's last MAX_CITATION_EXCERPT_CHARS
    assert len(content) - content.find("100 リクエスト") < MAX_CITATION_EXCERPT_CHARS
    assert "\n" not in content  # one paragraph, no line breaks

    window = select_excerpt_window(content, "レート制限はいくつですか")
    assert "100 リクエスト" in window
    assert len(window) <= MAX_CITATION_EXCERPT_CHARS


def test_tail_window_opens_on_a_sentence_boundary_not_mid_sentence():
    answer = "無料枠の上限は 1 か月あたり 5000 件までと定められている。"
    content = "概要。" + _LEAD + answer
    window = select_excerpt_window(content, "無料枠の上限はいくつですか")
    start = content.index(window)
    assert start == 0 or content[start - 1] in "\n。！？．"


def test_fallback_and_c1270_centring_unchanged():
    # top fallback for empty / unmatched query
    content = "概要。" + _LEAD + "答えの一文。"
    assert select_excerpt_window(content, "") == content[:MAX_CITATION_EXCERPT_CHARS]
    assert select_excerpt_window(content, "無関係 zzz") == content[:MAX_CITATION_EXCERPT_CHARS]
    # a mid-paragraph answer (C-1270) still centres
    mid = _FILLER * 40 + "重要: バックアップは毎日午前 3 時に実行されます。" + "その後の説明。" * 20
    assert "バックアップは毎日午前 3 時" in select_excerpt_window(mid, "バックアップの実行時刻はいつですか")
