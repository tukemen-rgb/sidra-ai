"""C-1222: a generated document must not open with a mid-list number.

An excerpt window that landed inside an ordered list left 「2. ブランドを
分けるか」 as a document's first line, because ``plain_text`` stripped
bullets but not ordered-list numbers. The marker strip now covers ordered
markers too, while an inline decimal (「3.5 倍」) and a four-digit year
(「2024.」) are left alone.
"""

from __future__ import annotations

from sidra_ai.creation.evidence import plain_text
from sidra_ai.evals.document_list_markers import evaluate_document_list_markers


def test_document_list_markers_eval_passes():
    result = evaluate_document_list_markers()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5


def test_plain_text_strips_ordered_list_markers_at_line_start():
    src = "2. 最初の案。\n3) 次の案。\n本文はここ。"
    out = plain_text(src)
    assert out == "最初の案。 次の案。 本文はここ。"


def test_plain_text_keeps_inline_decimal_and_year():
    assert plain_text("速度は 3.5 倍になった") == "速度は 3.5 倍になった"
    assert plain_text("3.5 倍に伸びた") == "3.5 倍に伸びた"
    assert plain_text("2024. 振り返り") == "2024. 振り返り"


def test_plain_text_still_strips_bullets():
    assert plain_text("- やること\n* 別の項目") == "やること 別の項目"
