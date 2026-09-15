"""C-1847: asked to delete, the product says it does not delete.

One request used to get three different answers about something else - the
changeable-settings list, the kind refusal, or the no-evidence boilerplate -
and none of them mentioned deletion. Deletion stays unimplemented; it is
destructive and belongs to the owner's decision.
"""

from __future__ import annotations

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.revise import asks_to_delete
from sidra_ai.evals.delete_says_it_cannot import (
    DELETE_REQUESTS,
    NOT_DELETIONS,
    evaluate_delete_says_it_cannot,
)
from sidra_ai.ingestion.state import StateStore


@pytest.fixture()
def service(tmp_path) -> SidraService:
    svc = SidraService(
        Settings(data_dir=str(tmp_path), model_backend="echo"),
        state_store=StateStore(tmp_path / "state.json"),
    )
    svc.chat("猫のゲームを作って")
    return svc


def test_delete_refusal_eval_passes():
    result = evaluate_delete_says_it_cannot()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


@pytest.mark.parametrize("request_text", DELETE_REQUESTS)
def test_every_phrasing_says_deletion_is_not_offered(service, request_text, tmp_path):
    before = {path.name for path in (tmp_path / "artifacts").iterdir()}

    result = service.chat(request_text)

    assert result["refusal"] == "delete_unsupported"
    assert "何も消していません" in result["answer"]
    assert before <= {path.name for path in (tmp_path / "artifacts").iterdir()}


def test_the_answer_does_not_print_the_machine_path(service, tmp_path):
    answer = service.chat("さっきのゲームを消して")["answer"]

    assert "artifacts/" in answer
    assert str(tmp_path) not in answer


@pytest.mark.parametrize("message", NOT_DELETIONS)
def test_turning_a_feature_off_is_not_deleting_the_artifact(message):
    assert asks_to_delete(message) is False


def test_the_sound_request_keeps_its_own_answer(service):
    assert service.chat("さっきのゲームの音を消して")["refusal"] == "revision_change"


def test_a_genuine_revision_still_works(service):
    assert service.chat("さっきのゲームを難しくして")["refused"] is False
