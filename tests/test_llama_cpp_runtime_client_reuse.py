from __future__ import annotations

import sys
from types import SimpleNamespace

from sidra_ai.models.base import GenerationRequest, GenerationResult, LocalModelAdapter
from sidra_ai.models.llama_runtime import LlamaCppRuntimeGuard


class _FakeLlamaCppAdapter(LocalModelAdapter):
    backend = "llama_cpp"

    def __init__(self) -> None:
        super().__init__("fake-llama")
        self.endpoint = "http://127.0.0.1:8080"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        raise AssertionError("generation is not part of this transport test")


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "default_generation_settings": {"n_ctx": 2048},
            "total_slots": 1,
        }


def test_runtime_props_client_is_lazy_proxy_isolated_and_reused(monkeypatch) -> None:
    created_clients: list[object] = []

    class _FakeClient:
        def __init__(self, **kwargs: object) -> None:
            self.init_kwargs = kwargs
            self.get_calls: list[tuple[str, dict[str, object]]] = []
            created_clients.append(self)

        def get(self, url: str, **kwargs: object) -> _FakeResponse:
            self.get_calls.append((url, kwargs))
            return _FakeResponse()

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(Client=_FakeClient))

    guard = LlamaCppRuntimeGuard(
        _FakeLlamaCppAdapter(),
        expected_context_tokens=2048,
    )

    assert created_clients == []
    assert guard._fetch_props()["total_slots"] == 1
    assert guard._fetch_props()["total_slots"] == 1

    assert len(created_clients) == 1
    client = created_clients[0]
    assert client.init_kwargs == {"trust_env": False}
    assert client.get_calls == [
        ("http://127.0.0.1:8080/props", {"timeout": 3.0}),
        ("http://127.0.0.1:8080/props", {"timeout": 3.0}),
    ]
