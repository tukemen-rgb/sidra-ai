"""C-1212: evidence is quoted as prose, not as raw Markdown.

The corpus is Markdown, so excerpt windows dragged ``##``, ``**`` and ``>``
into slide bullets and document quotes as literal characters. The flatten
happens once, in ``_facts_for``; /v1/chat citation excerpts stay raw so a
reviewer can match them byte-for-byte against the source.
"""

from __future__ import annotations

from sidra_ai.creation.evidence import plain_text
from sidra_ai.evals.fact_text_plain import evaluate_fact_text_plain


def test_heading_bold_quote_and_code_are_flattened():
    assert plain_text("## 運用メモ - 毎日 1 本") == "運用メモ - 毎日 1 本"
    assert plain_text("**事前に本人へ一言** を徹底") == "事前に本人へ一言 を徹底"
    assert plain_text("> 引用された行です") == "引用された行です"
    assert plain_text("`normalize` を通す") == "normalize を通す"


def test_ambiguous_characters_survive():
    # Arithmetic stars, paths and lone markers are content, not decoration.
    assert plain_text("x*y と 2*3 は残る") == "x*y と 2*3 は残る"
    assert plain_text("掲載実績は 21,907 件") == "掲載実績は 21,907 件"


def test_fact_text_plain_eval_passes():
    result = evaluate_fact_text_plain()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6
