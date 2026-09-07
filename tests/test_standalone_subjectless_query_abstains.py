"""C-1468: a subject-less query with no history abstains instead of citing glue.

The standalone twin of C-1453: 「もっと詳しく」 as a first message (or after the
client dropped history) has no subject and no previous question to carry, so a
generic glue hit was cited as fact. The floor now abstains; the with-history
carry (C-1453) is untouched.
"""

from __future__ import annotations

import pytest

from sidra_ai.evals.standalone_subjectless_query_abstains import (
    _service,
    evaluate_standalone_subjectless_query_abstains,
)


def _paths(result):
    return [c["path"] for c in result["citations"]]


def test_standalone_subjectless_eval_passes():
    result = evaluate_standalone_subjectless_query_abstains()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


@pytest.mark.parametrize("query", ["もっと詳しく", "詳しく教えて", "詳しく", "続けて", "教えて"])
def test_standalone_subjectless_abstains(query):
    svc = _service()
    assert _paths(svc.chat(query)) == []


def test_standalone_subject_query_unchanged():
    svc = _service()
    assert _paths(svc.chat("デプロイの承認は誰がしますか"))[:1] == ["docs/deploy.md"]


def test_with_history_carry_preserved():
    svc = _service()
    q1 = "デプロイの承認は誰がしますか"
    hist = [(q1, svc.chat(q1)["answer"])]
    assert _paths(svc.chat("もっと詳しく", history=hist))[:1] == ["docs/deploy.md"]
