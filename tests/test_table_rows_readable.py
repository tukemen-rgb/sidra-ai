"""C-1245: a cited multi-row Markdown table keeps its rows apart.

C-1226 joined a table's cells with 「 / 」 but plain_text's final
``" ".join(text.split())`` collapsed the newlines between rows, so a multi-row
table ran together (「項目 / 内容 運営歴 / 約20年 核 / …」) and the row break
looked exactly like the 「 / 」 inside a row. Each flattened row now ends with a
delimiter that survives the collapse, so the rows read as rows.
"""

from __future__ import annotations

from sidra_ai.creation.evidence import plain_text, whole_sentences
from sidra_ai.evals.table_rows_readable import evaluate_table_rows_readable


def test_table_rows_readable_eval_passes():
    result = evaluate_table_rows_readable()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 7


def test_multi_row_table_rows_are_separated():
    out = plain_text(
        "集計。\n| 項目 | 値 |\n| --- | --- |\n"
        "| 総数 | 21,907 件 |\n| ページ数 | 25,581 |\n"
    )
    # cells within a row still joined
    assert "項目 / 値" in out
    assert "総数 / 21,907 件" in out
    # rows no longer run together: neither the space form nor the / form of the
    # between-row boundary appears.
    assert "値 総数" not in out
    assert "値 / 総数" not in out
    assert "件 ページ数" not in out
    # numbers survive
    assert "21,907" in out and "25,581" in out


def test_row_delimiter_is_not_a_sentence_boundary():
    # A row break must not truncate the excerpt as if it were a sentence end.
    out = plain_text("| 項目 | 値 |\n| --- | --- |\n| 総数 | 21,907 件 |\n")
    assert whole_sentences(out) != ""
    # both rows survive whole_sentences (the delimiter is not 。！？)
    assert "項目 / 値" in whole_sentences(out)
    assert "総数 / 21,907 件" in whole_sentences(out)


def test_non_table_lines_untouched():
    assert plain_text("選択肢は a|b の形式") == "選択肢は a|b の形式"
    assert plain_text("ふつうの文。") == "ふつうの文。"
