"""Model backend failures must not expose local runtime diagnostics."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.ingestion.state import StateStore
from sidra_ai.models.base import ModelUnavailableError


_PRIVATE_DIAGNOSTIC = (
    "ollama backend at http://127.0.0.1:11434 is unreachable: "
    "private-local-runtime-detail"
)


def _service(settings, store, gate, client, model, tmp_path) -> SidraService:
    return SidraService(
        settings,
        model=model,
        store=store,
        gate=gate,
        client=client,
        state_store=StateStore(tmp_path / "state.json"),
    )


def _fail_generation(*_args, **_kwargs):
    raise ModelUnavailableError(_PRIVATE_DIAGNOSTIC)


def test_chat_refusal_does_not_reflect_model_backend_diagnostics(
    settings: Settings,
    store,
    gate,
    client,
    model,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(settings, store, gate, client, model, tmp_path)
    monkeypatch.setattr(service.model, "generate", _fail_generation)

    response = TestClient(create_app(service, settings)).post(
        "/v1/chat", json={"message": "summarize the available evidence"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is True
    assert body["answer"] == ""
    assert body["reason"] == "model backend unavailable"
    assert "127.0.0.1:11434" not in response.text
    assert "private-local-runtime-detail" not in response.text


def test_github_analyze_inherits_model_error_redaction(
    settings: Settings,
    store,
    gate,
    client,
    model,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(settings, store, gate, client, model, tmp_path)
    monkeypatch.setattr(service.model, "generate", _fail_generation)

    response = TestClient(create_app(service, settings)).post(
        "/v1/github/analyze", json={"repositories": ["tukemen-rgb/site"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis"] is not None
    assert body["analysis"]["refused"] is True
    assert body["analysis"]["reason"] == "model backend unavailable"
    assert "127.0.0.1:11434" not in response.text
    assert "private-local-runtime-detail" not in response.text
