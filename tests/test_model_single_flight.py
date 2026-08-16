"""Concurrency regressions for constrained local-model generation."""

from __future__ import annotations

import threading

import pytest

from sidra_ai.models.base import (
    GenerationChunk,
    GenerationRequest,
    GenerationResult,
    LocalModelAdapter,
)
from sidra_ai.models.routing import (
    HardwareBudget,
    LocalModelCandidate,
    route_and_create_adapter,
)
from sidra_ai.models.singleflight import (
    ModelBusyError,
    SingleFlightLocalModelAdapter,
)


def _request() -> GenerationRequest:
    return GenerationRequest(system_prompt="system", user_message="question")


def test_second_generation_is_rejected_while_first_is_active() -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingAdapter(LocalModelAdapter):
        backend = "blocking"

        def __init__(self) -> None:
            super().__init__("local")
            self.calls = 0

        def generate(self, request: GenerationRequest) -> GenerationResult:
            self.calls += 1
            started.set()
            if not release.wait(timeout=2.0):
                raise AssertionError("test did not release the first generation")
            return GenerationResult(text="ok", backend=self.backend, model=self.model)

    inner = BlockingAdapter()
    adapter = SingleFlightLocalModelAdapter(inner)
    failures: list[BaseException] = []

    def run_first() -> None:
        try:
            adapter.generate(_request())
        except BaseException as exc:  # pragma: no cover - surfaced by assertion below
            failures.append(exc)

    thread = threading.Thread(target=run_first)
    thread.start()
    assert started.wait(timeout=1.0)

    with pytest.raises(ModelBusyError, match="in-flight"):
        adapter.generate(_request())

    release.set()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert failures == []
    assert inner.calls == 1

    # Completion returns the admission slot to the next request.
    result = adapter.generate(_request())
    assert result.text == "ok"
    assert inner.calls == 2


def test_stream_holds_slot_until_consumer_closes_generator() -> None:
    class StreamingAdapter(LocalModelAdapter):
        backend = "streaming"
        supports_streaming = True

        def __init__(self) -> None:
            super().__init__("local")
            self.generate_calls = 0

        def generate(self, request: GenerationRequest) -> GenerationResult:
            self.generate_calls += 1
            return GenerationResult(text="ok", backend=self.backend, model=self.model)

        def generate_stream(self, request: GenerationRequest):
            yield GenerationChunk(
                text_delta="partial",
                backend=self.backend,
                model=self.model,
            )
            yield GenerationChunk(
                text_delta="done",
                backend=self.backend,
                model=self.model,
                done=True,
            )

    inner = StreamingAdapter()
    adapter = SingleFlightLocalModelAdapter(inner)
    stream = adapter.generate_stream(_request())

    assert next(stream).text_delta == "partial"
    with pytest.raises(ModelBusyError, match="in-flight"):
        adapter.generate(_request())

    # A client disconnect/early close must not permanently consume the slot.
    stream.close()
    assert adapter.generate(_request()).text == "ok"
    assert inner.generate_calls == 1


def test_routed_adapter_enforces_single_flight_and_context_cap() -> None:
    routed = route_and_create_adapter(
        [
            LocalModelCandidate(
                backend="echo",
                model="sidra-local-test",
                weights_vram_mib=1024,
                kv_cache_mib_per_1k_tokens=64,
                max_context_tokens=4096,
                quantization="Q4_TEST",
            )
        ],
        hardware=HardwareBudget(vram_mib=6144, reserve_vram_mib=512),
        planned_context_tokens=2048,
    )

    assert isinstance(routed.adapter, SingleFlightLocalModelAdapter)
    assert routed.adapter.max_context_tokens == 2048
    assert routed.adapter.requires_paid_api is False
    assert routed.adapter.health()["single_flight_generation"] is True
