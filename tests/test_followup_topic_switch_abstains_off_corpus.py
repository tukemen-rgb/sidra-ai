"""C-1481: a mid-conversation switch to an uncovered subject abstains.

The history-carry fired for a follow-up naming a NEW subject the corpus does not
cover, so the previous topic's documents were served as the answer. The floor
now abstains when the carry happened, the follow-up has its own content subject,
and the evidence mentions none of it - while a pure elaboration still carries and
a covered new subject still grounds on itself.
"""

from __future__ import annotations

from sidra_ai.evals.followup_topic_switch_abstains_off_corpus import (
    _service,
    evaluate_followup_topic_switch_abstains_off_corpus,
)

_DEPLOY = "docs/deploy.md"
_MARKETING = "docs/marketing.md"


def _paths(result):
    return [c["path"] for c in result["citations"]]


def test_topic_switch_eval_passes():
    result = evaluate_followup_topic_switch_abstains_off_corpus()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_off_corpus_switch_abstains_instead_of_bleeding():
    svc = _service()
    q1 = "デプロイの承認は誰がしますか"
    hist = [(q1, svc.chat(q1)["answer"])]
    off = svc.chat("料金プランを教えて", history=hist)
    assert off["citations"] == []
    assert "十分な根拠がありません" in off["answer"]
    assert "承認" not in off["answer"]


def test_elaboration_still_carries():
    svc = _service()
    q1 = "デプロイの承認は誰がしますか"
    hist = [(q1, svc.chat(q1)["answer"])]
    assert _paths(svc.chat("もっと詳しく", history=hist))[:1] == [_DEPLOY]


def test_covered_new_subject_still_grounds_on_itself():
    svc = _service()
    q1 = "デプロイの承認は誰がしますか"
    hist = [(q1, svc.chat(q1)["answer"])]
    mk = svc.chat("マーケティングのレポートは？", history=hist)
    assert _paths(mk)[:1] == [_MARKETING]
    assert _DEPLOY not in _paths(mk)
