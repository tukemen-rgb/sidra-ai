"""C-1264: a clipped citation excerpt is marked with 「…」, within the cap.

A chunk longer than MAX_CITATION_EXCERPT_CHARS came back as a bare 200-char
slice cut mid-word, with no sign it was clipped. It now carries 「…」 where it
drops the head or the tail, stays within the cap, and a chunk that fits is
returned unchanged.
"""

from __future__ import annotations

from sidra_ai.api.citations import citation_excerpt
from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS
from sidra_ai.evals.citation_excerpt_marks_truncation import (
    evaluate_citation_excerpt_marks_truncation,
)
from sidra_ai.security.output_guard import OutputGuard


def test_citation_excerpt_marks_truncation_eval_passes():
    result = evaluate_citation_excerpt_marks_truncation()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_tail_clip_is_marked_and_within_cap():
    content = "返金方針。" + "".join(f"第{i}条 返金は 14 日以内。" for i in range(1, 20))
    excerpt, withheld = citation_excerpt(content, OutputGuard(), query="返金")
    assert not withheld
    assert excerpt.endswith("…")
    assert not excerpt.startswith("…")  # head window starts at 0
    assert len(excerpt) <= MAX_CITATION_EXCERPT_CHARS


def test_head_clip_is_marked_when_window_moves_down():
    lines = ["無関係な冒頭。" * 3]
    lines += [f"段落{i}: 説明。" * 3 for i in range(1, 12)]
    lines += ["ペンギンの飼育の詳細をここに書く。" * 3]
    lines += [f"末尾{i}: 説明。" * 3 for i in range(1, 12)]
    content = "\n".join(lines)
    excerpt, _ = citation_excerpt(content, OutputGuard(), query="ペンギン")
    assert excerpt.startswith("…")
    assert len(excerpt) <= MAX_CITATION_EXCERPT_CHARS


def test_chunk_that_fits_is_unchanged():
    short = "料金は無料・プロの 2 種類です。"
    excerpt, _ = citation_excerpt(short, OutputGuard(), query="料金")
    assert excerpt == short
    assert "…" not in excerpt
