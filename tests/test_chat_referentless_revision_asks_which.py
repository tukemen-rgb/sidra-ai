"""C-1797: a referent-less change instruction asks which artifact, not "no evidence".

「もっと難しくして」 with no それ/さっきの is a change instruction that names no
target; chat now returns refusal=="revision_target" (asks which), not the
no-evidence abstention. A properly referenced revision and a real question are
unaffected.
"""

from __future__ import annotations

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.chat_referentless_revision_asks_which import (
    evaluate_chat_referentless_revision_asks_which,
)
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

_REPO = "tukemen-rgb/sidra-ai"


@pytest.fixture
def service(tmp_path) -> SidraService:
    settings = Settings(allowed_repositories=(_REPO,), data_dir=str(tmp_path / "sidra"))
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=(_REPO,),
        quarantine_store=QuarantineStore(tmp_path / "q.jsonl"),
    )
    return SidraService(settings, store=DocumentStore(gate), gate=gate)


def test_referentless_revision_eval_passes():
    result = evaluate_chat_referentless_revision_asks_which()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_a_bare_harder_asks_which(service: SidraService):
    reply = service.chat("もっと難しくして")
    assert reply["refusal"] == "revision_target"
    assert "現時点では十分な根拠がありません" not in reply["answer"]
    assert "/v1/github/analyze" not in reply["answer"]


def test_a_bare_rename_asks_which(service: SidraService):
    assert service.chat("タイトルを「夜のレース」にして")["refusal"] == "revision_target"


def test_a_real_question_is_not_asked_back(service: SidraService):
    assert service.chat("火星の天気を教えて")["refusal"] != "revision_target"


def test_a_referenced_revision_is_not_asked_back(service: SidraService):
    assert service.chat("さっきのゲームを難しくして")["refusal"] != "revision_target"
