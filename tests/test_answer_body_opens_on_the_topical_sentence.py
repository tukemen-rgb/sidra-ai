"""C-1911: the answer body opens on the topical sentence, not one sharing a
low-value word.

"How are deployments done?" opened the answer on "Rollbacks are done with
kubectl rollout undo" - a distractor that shared the low-value word "done" -
because the salient word "deployments" never matched "Deployment" over a bare
plural. The opening score now folds a trailing plural s on both sides (retrieval
untouched), so the topical sentence wins.
"""

from __future__ import annotations

import pytest

from sidra_ai.evals.answer_body_opens_on_the_topical_sentence import (
    _ABSENT,
    _PRESENT,
    _answer_of,
    evaluate_answer_body_opens_on_the_topical_sentence,
)
from sidra_ai.models.echo import _fold_plural


def test_eval_passes():
    result = evaluate_answer_body_opens_on_the_topical_sentence()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


@pytest.mark.parametrize("content,query,needle", _PRESENT)
def test_topical_sentence_present(content, query, needle):
    assert needle in _answer_of(content, query)


@pytest.mark.parametrize("content,query,needle", _ABSENT)
def test_distractor_sentence_absent(content, query, needle):
    assert needle not in _answer_of(content, query)


def test_deployments_question_gives_the_deployment_description():
    answer = _answer_of(
        "Deployment uses GitHub Actions. "
        "The pipeline runs tests, builds a Docker image, and pushes to the registry. "
        "Rollbacks are done with kubectl rollout undo.",
        "How are deployments done?",
    )
    assert "GitHub Actions" in answer
    assert "rollout undo" not in answer


def test_fold_plural_is_guarded():
    # Folds a real plural...
    assert _fold_plural("deployments") == "deployment"
    assert _fold_plural("releases") == "release"
    # ...but leaves short words and ss-endings alone.
    assert _fold_plural("is") == "is"
    assert _fold_plural("process") == "process"
    assert _fold_plural("access") == "access"
    assert _fold_plural("done") == "done"
