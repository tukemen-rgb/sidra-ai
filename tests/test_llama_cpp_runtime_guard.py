from __future__ import annotations

from collections.abc import Iterator

import pytest

from sidra_ai.models.base import (
    GenerationChunk,
    GenerationRequest,
    GenerationResult,
    LocalModelAdapter,
    ModelUnavailableError,
)
from sidra_ai.models.budgeted import BudgetedLocalModelAdapter
from sidra_ai.models.llama_runtime import LlamaCppRuntimeGuard
from sidra_ai.models.registry import create_adapter


class _FakeLlamaCppAdapter(LocalModelAdapter):
    backend = "llama_cpp"
    supports_streaming = True

    def __init__(self) -> None:
        super().__init__("fake-llama")
        self.endpoint = "http://127.0.0.1:8080"
        self.generate_calls = 0
        self.stream_calls = 0

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.generate_calls += 1
        return GenerationResult(
            text="ok",
            backend=self.backend,
            model=self.model,
            input_tokens_estimate=1,
            output_tokens_estimate=1,
            metadata={"cost_usd": 0.0},
        )

    def generate_stream(self, request: GenerationRequest) -> Iterator[GenerationChunk]:
        self.stream_calls += 1
        yield GenerationChunk(
            text_delta="ok",
            backend=self.backend,
            model=self.model,
            done=True,
            input_tokens_estimate=1,
            output_tokens_estimate=1,
            finish_reason="stop",
            metadata={"cost_usd": 0.0},
        )

    def health(self) -> dict[str, object]:
        return {"available": True, "backend": self.backend, "model": self.model}


def _props(*, n_ctx: int = 2048, total_slots: int = 1) -> dict[str, object]:
    return {
        "default_generation_settings": {"n_ctx": n_ctx},
        "total_slots": total_slots,
    }


def _request() -> GenerationRequest:
    return GenerationRequest(system_prompt="system", user_message="question")


def test_routed_llama_cpp_adapter_is_runtime_guarded() -> None:
    adapter = create_adapter(
        "llama_cpp",
        "local-model",
        max_context_tokens=2048,
    )

    assert isinstance(adapter, BudgetedLocalModelAdapter)
    assert isinstance(adapter.inner, LlamaCppRuntimeGuard)
    assert adapter.inner.expected_context_tokens == 2048


def test_guard_allows_matching_single_slot_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = _FakeLlamaCppAdapter()
    guard = LlamaCppRuntimeGuard(inner, expected_context_tokens=2048)
    monkeypatch.setattr(guard, "_fetch_props", lambda: _props())

    result = guard.generate(_request())

    assert result.text == "ok"
    assert inner.generate_calls == 1


def test_guard_rejects_context_mismatch_before_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = _FakeLlamaCppAdapter()
    guard = LlamaCppRuntimeGuard(inner, expected_context_tokens=2048)
    monkeypatch.setattr(guard, "_fetch_props", lambda: _props(n_ctx=4096))

    with pytest.raises(ModelUnavailableError, match="context does not match"):
        guard.generate(_request())

    assert inner.generate_calls == 0


def test_guard_rejects_multiple_server_slots_before_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = _FakeLlamaCppAdapter()
    guard = LlamaCppRuntimeGuard(inner, expected_context_tokens=2048)
    monkeypatch.setattr(guard, "_fetch_props", lambda: _props(total_slots=2))

    with pytest.raises(ModelUnavailableError, match="exactly one server slot"):
        guard.generate(_request())

    assert inner.generate_calls == 0


def test_guard_rejects_malformed_runtime_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = _FakeLlamaCppAdapter()
    guard = LlamaCppRuntimeGuard(inner, expected_context_tokens=2048)
    monkeypatch.setattr(
        guard,
        "_fetch_props",
        lambda: {"default_generation_settings": {"n_ctx": "2048"}, "total_slots": 1},
    )

    with pytest.raises(ModelUnavailableError, match="properties are invalid"):
        guard.generate(_request())

    assert inner.generate_calls == 0


def test_streaming_validates_runtime_before_backend_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = _FakeLlamaCppAdapter()
    guard = LlamaCppRuntimeGuard(inner, expected_context_tokens=2048)
    monkeypatch.setattr(guard, "_fetch_props", lambda: _props(total_slots=2))

    with pytest.raises(ModelUnavailableError, match="exactly one server slot"):
        list(guard.generate_stream(_request()))

    assert inner.stream_calls == 0


def test_unbudgeted_low_level_llama_cpp_adapter_is_not_wrapped() -> None:
    adapter = create_adapter("llama_cpp", "local-model")

    assert not isinstance(adapter, LlamaCppRuntimeGuard)
