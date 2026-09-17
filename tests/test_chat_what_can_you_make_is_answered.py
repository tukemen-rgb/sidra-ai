"""C-1923: a "what can you make" capability question is answered, not walled.

「何が作れますか」「作れるものは」 fell to the no-evidence wall though the help
answer already names what can be made. They now reach the help branch, in the
request's language; a real make request still creates.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sidra_ai.api.service import SidraService, _is_help_query
from sidra_ai.config.settings import Settings
from sidra_ai.evals.chat_what_can_you_make_is_answered import (
    EN_CAPABILITY,
    JP_CAPABILITY,
    NOT_CAPABILITY,
    evaluate_chat_what_can_you_make_is_answered,
)
from sidra_ai.ingestion.state import StateStore


@pytest.fixture()
def service(tmp_path) -> SidraService:
    return SidraService(
        Settings(data_dir=str(tmp_path), model_backend="echo"),
        state_store=StateStore(tmp_path / "state.json"),
    )


def test_eval_passes():
    result = evaluate_chat_what_can_you_make_is_answered()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 12


@pytest.mark.parametrize("question", JP_CAPABILITY)
def test_japanese_capability_is_help(service, question):
    r = service.chat(question)
    assert r["refusal"] == "help"
    assert "作れる" in r["answer"]
    assert "/v1/github/analyze" not in r["answer"]


@pytest.mark.parametrize("question", EN_CAPABILITY)
def test_english_capability_is_help(question):
    assert _is_help_query(question) is True


@pytest.mark.parametrize("question", NOT_CAPABILITY)
def test_make_request_is_not_help(service, question):
    assert service.chat(question)["refusal"] != "help"
