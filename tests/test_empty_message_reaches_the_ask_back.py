"""C-1536: an empty /v1/chat message reaches the C-1515 ask-back, not a bare 422."""

from __future__ import annotations

import tempfile

from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.empty_message_reaches_the_ask_back import (
    evaluate_empty_message_reaches_the_ask_back,
)
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.gate import GatePolicy, SecurityGate


def _client(tmp_path):
    settings = Settings(data_dir=str(tmp_path / "s"))
    gate = SecurityGate(GatePolicy(), allowed_repositories=("acme/app",))
    svc = SidraService(settings, model=EchoModelAdapter(),
                       store=DocumentStore(gate), gate=gate)
    return TestClient(create_app(svc, settings))


def test_eval_passes():
    result = evaluate_empty_message_reaches_the_ask_back()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 7


def test_http_empty_reaches_ask_back(tmp_path):
    r = _client(tmp_path).post("/v1/chat", json={"message": ""})
    assert r.status_code == 200
    assert r.json().get("refusal") == "empty"
    assert "質問が空" in r.json().get("answer", "")


def test_length_cap_still_enforced(tmp_path):
    r = _client(tmp_path).post("/v1/chat", json={"message": "あ" * 32_001})
    assert r.status_code == 422
