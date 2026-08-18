from __future__ import annotations

from sidra_ai.models.base import GenerationRequest, GenerationResult, LocalModelAdapter
from sidra_ai.models.benchmark import run_benchmark


class _BenchmarkAdapter(LocalModelAdapter):
    backend = "test_benchmark"

    def __init__(self, events: list[str]) -> None:
        super().__init__("fixture", quantization="test")
        self._events = events

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self._events.append("generate")
        return GenerationResult(
            text="done",
            backend=self.backend,
            model=self.model,
            input_tokens_estimate=8,
            output_tokens_estimate=4,
        )


def test_peak_memory_readout_stays_outside_generation_timing() -> None:
    events: list[str] = []
    memory_samples = iter([1000.0, 1100.0])
    ticks = iter([10.0, 11.0])

    def memory_probe() -> float:
        events.append("memory")
        return next(memory_samples)

    def clock() -> float:
        events.append("clock")
        return next(ticks)

    def peak_memory_probe() -> float:
        events.append("peak")
        return 1450.0

    result = run_benchmark(
        _BenchmarkAdapter(events),
        GenerationRequest(system_prompt="system", user_message="question"),
        memory_probe=memory_probe,
        peak_memory_probe=peak_memory_probe,
        clock=clock,
    )

    assert events == ["memory", "clock", "generate", "clock", "memory", "peak"]
    assert result.total_time_s == 1.0
    assert result.memory_before_mib == 1000.0
    assert result.memory_after_mib == 1100.0
    assert result.memory_delta_mib == 100.0
    assert result.memory_peak_mib == 1450.0
    assert result.to_dict()["memory_peak_mib"] == 1450.0


def test_peak_memory_never_undercuts_endpoint_observations() -> None:
    memory_samples = iter([1200.0, 1300.0])
    ticks = iter([20.0, 21.0])

    result = run_benchmark(
        _BenchmarkAdapter([]),
        GenerationRequest(system_prompt="system", user_message="question"),
        memory_probe=lambda: next(memory_samples),
        peak_memory_probe=lambda: 900.0,
        clock=lambda: next(ticks),
    )

    assert result.memory_peak_mib == 1300.0
