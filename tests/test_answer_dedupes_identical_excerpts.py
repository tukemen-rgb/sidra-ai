"""C-1241: the answer shows an identical excerpt once, not once per source.

Two files carrying the same passage produced two blocks with identical text and
the answer printed the paragraph twice. The echo answer now shows the excerpt
once and points a later duplicate back to it; the footer still lists every
source. Distinct excerpts are untouched, and the note follows the language.
"""

from __future__ import annotations

from sidra_ai.evals.answer_dedupes_identical_excerpts import (
    evaluate_answer_dedupes_identical_excerpts,
)
from sidra_ai.models.base import GenerationRequest
from sidra_ai.models.echo import EchoModelAdapter


def _block(label: str, citation: str, content: str) -> str:
    return (
        f"<<<SIDRA_DATA_BLOCK {label}>>>\nsource: {citation}\ntrust: DATA\n"
        f"content:\n{content}\n<<<END_SIDRA_DATA_BLOCK {label}>>>"
    )


def _answer(question: str, blocks: list[str]) -> str:
    req = GenerationRequest(system_prompt="", user_message=question, data_context="\n".join(blocks))
    return EchoModelAdapter().generate(req).text


def test_answer_dedupe_eval_passes():
    result = evaluate_answer_dedupes_identical_excerpts()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


def test_identical_excerpt_shown_once_footer_keeps_both():
    dup = "要判断の項目は人が決めるまで着手しない方針である。"
    ans = _answer(
        "方針は？",
        [_block("S1", "repo@x:TODO.md", dup), _block("S2", "repo@x:report.md", dup)],
    )
    assert ans.count(dup) == 1
    assert "S1 と同じ内容" in ans
    footer = ans.rsplit("\n", 1)[-1]
    assert "[S1]" in footer and "[S2]" in footer


def test_distinct_excerpts_not_collapsed():
    ans = _answer(
        "検査は？",
        [
            _block("S1", "repo@x:a.md", "検査は 1GB のメモリを使う。"),
            _block("S2", "repo@x:b.md", "レート制限は 6 バースト。"),
        ],
    )
    assert "検査は 1GB のメモリを使う。" in ans
    assert "レート制限は 6 バースト。" in ans
    assert "同じ内容" not in ans
