"""C-1927: a message with no content asks back instead of hitting the wall.

"..." / "？？？" / "🎮" slipped past the whitespace-only empty check, reached
retrieval, and got the no-evidence wall (ingest a repository). The empty check
now catches any message with no alphanumeric/CJK content; 犬/8080/OAuth2 are
untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.chat_contentless_message_asks_back import (
    CONTENTLESS,
    HAS_CONTENT,
    WHITESPACE,
    evaluate_chat_contentless_message_asks_back,
)
from sidra_ai.ingestion.state import StateStore


@pytest.fixture()
def service(tmp_path) -> SidraService:
    return SidraService(
        Settings(data_dir=str(tmp_path), model_backend="echo"),
        state_store=StateStore(tmp_path / "state.json"),
    )


def test_eval_passes():
    result = evaluate_chat_contentless_message_asks_back()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 19


@pytest.mark.parametrize("message", CONTENTLESS)
def test_contentless_asks_back(service, message):
    r = service.chat(message)
    assert r["refusal"] == "empty"
    assert "/v1/github/analyze" not in r["answer"]


@pytest.mark.parametrize("message", HAS_CONTENT)
def test_content_is_not_empty(service, message):
    assert service.chat(message).get("refusal") != "empty"


@pytest.mark.parametrize("message", WHITESPACE)
def test_whitespace_still_asks_back(service, message):
    assert service.chat(message)["refusal"] == "empty"
