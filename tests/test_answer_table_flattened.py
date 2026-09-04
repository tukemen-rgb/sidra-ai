"""C-1226: a cited Markdown table must read as prose, not a wall of bars.

「ページ数はいくつですか」 returned 「… | 項目 | 値 | | --- | --- | |
収集ゲーム総数 | 21,907 件 | …」 - the README stats table with its pipes and
separator row. ``plain_text`` now drops the separator row and joins each
row's cells with 「 / 」, while a mid-sentence pipe (「a|b」) is left alone.
"""

from __future__ import annotations

from sidra_ai.creation.evidence import plain_text
from sidra_ai.evals.answer_table_flattened import evaluate_answer_table_flattened


def test_answer_table_flattened_eval_passes():
    result = evaluate_answer_table_flattened()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5


def test_plain_text_flattens_a_table():
    table = (
        "集計\n"
        "| 項目 | 値 |\n"
        "| --- | --- |\n"
        "| 総数 | 21,907 件 |\n"
    )
    out = plain_text(table)
    assert "|" not in out
    assert "---" not in out
    assert "項目 / 値" in out
    assert "総数 / 21,907 件" in out


def test_plain_text_keeps_a_mid_sentence_pipe():
    assert plain_text("選択肢は a|b の形式") == "選択肢は a|b の形式"
