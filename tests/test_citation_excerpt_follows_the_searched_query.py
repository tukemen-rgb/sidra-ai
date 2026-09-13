"""C-1782: a follow-up's citation excerpt shows the passage under discussion.

A subjectless follow-up (「もっと詳しく」) retrieves on searched_query (prev +
query) but the excerpt was attached with the bare query, which scored every
window zero and fell back to the chunk opening. The excerpt now follows
searched_query; a single turn (searched_query == query) is unchanged.
"""

from __future__ import annotations

from sidra_ai.api.citations import MAX_CITATION_EXCERPT_CHARS
from sidra_ai.evals.citation_excerpt_follows_the_searched_query import (
    _CONTENT,
    _SUBJECT,
    _excerpt,
    _service,
    evaluate_citation_excerpt_follows_the_searched_query,
)


def test_excerpt_follows_searched_query_eval_passes():
    result = evaluate_citation_excerpt_follows_the_searched_query()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_followup_excerpt_shows_the_subject_not_the_opening():
    svc = _service()
    q = "デプロイはどうやって走りますか"
    direct = svc.chat(q)
    answer = (direct if isinstance(direct, dict) else direct.__dict__).get("answer", "")
    fu = svc.chat("もっと詳しく", history=[(q, answer)])
    ex = _excerpt(fu)
    opening = _CONTENT[:MAX_CITATION_EXCERPT_CHARS]
    assert _SUBJECT in ex
    assert ex != opening


def test_single_turn_excerpt_is_unchanged():
    svc = _service()
    ex = _excerpt(svc.chat("デプロイはどうやって走りますか"))
    assert _SUBJECT in ex
