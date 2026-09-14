"""C-1828: a subject-less follow-up's answer body shows the carried subject.

The multi-turn sibling of C-1827. 「もっと詳しく」 carries the previous question
into searched_query and the excerpt follows it (C-1782), but the answer body was
fed the bare turn, so it fell back to the chunk opening. The service now passes
the effective retrieval query to the model, so the body opens on the same passage
the excerpt does. Single turns are unchanged.
"""

from __future__ import annotations

from sidra_ai.evals.answer_body_follows_carried_subject import (
    _ANSWER_MARK,
    _service,
    evaluate_answer_body_follows_carried_subject,
)


def _answer(result) -> str:
    d = result if isinstance(result, dict) else result.__dict__
    return str(d.get("answer") or "")


def test_answer_body_follows_carried_subject_eval_passes():
    result = evaluate_answer_body_follows_carried_subject()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5


def test_followup_body_shows_the_carried_subject():
    svc = _service()
    q = "デプロイはどうやって走りますか"
    direct = svc.chat(q)
    history = [(q, _answer(direct))]
    followup = _answer(svc.chat("もっと詳しく", history=history))
    assert _ANSWER_MARK in followup
    assert "デプロイは" in followup


def test_single_turn_still_shows_its_subject():
    # regression guard: a direct question is unchanged by the carry plumbing
    svc = _service()
    assert _ANSWER_MARK in _answer(svc.chat("デプロイはどうやって走りますか"))
