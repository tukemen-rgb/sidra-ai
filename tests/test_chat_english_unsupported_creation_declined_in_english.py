"""C-1919: an English unsupported-creation request is declined in English.

"make an excel spreadsheet" / "build me a mobile app" got the Japanese decline
「制作のご依頼と受け取りましたが、この形式は作れません…」 with Japanese kind
labels. The decline now follows the request's language (rule 6); the Japanese
decline and the creation metadata are unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.chat_english_unsupported_creation_declined_in_english import (
    ENGLISH_UNSUPPORTED,
    JAPANESE_UNSUPPORTED,
    evaluate_chat_english_unsupported_creation_declined_in_english,
)
from sidra_ai.ingestion.state import StateStore


@pytest.fixture()
def service(tmp_path) -> SidraService:
    return SidraService(
        Settings(data_dir=str(tmp_path), model_backend="echo"),
        state_store=StateStore(tmp_path / "state.json"),
    )


def test_eval_passes():
    result = evaluate_chat_english_unsupported_creation_declined_in_english()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


@pytest.mark.parametrize("request_text", ENGLISH_UNSUPPORTED)
def test_english_request_declined_in_english(service, request_text):
    answer = service.chat(request_text)["answer"]
    assert "この形式は作れません" not in answer
    assert "制作のご依頼" not in answer
    assert "can't make that format" in answer


@pytest.mark.parametrize("request_text", ENGLISH_UNSUPPORTED)
def test_english_request_keeps_declined_metadata(service, request_text):
    outcome = (service.chat(request_text).get("creation") or {}).get("outcome") or {}
    assert outcome.get("declined") is True
    assert outcome.get("offered")


@pytest.mark.parametrize("request_text", JAPANESE_UNSUPPORTED)
def test_japanese_request_still_declined_in_japanese(service, request_text):
    assert "この形式は作れません" in service.chat(request_text)["answer"]
