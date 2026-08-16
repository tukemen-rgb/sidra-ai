"""Backend-agnostic local inference benchmarking.

The harness measures the signals needed to choose a model for constrained
owned hardware without sending prompts, results, or metrics to an external
service. It deliberately accepts an optional memory probe instead of taking
a hard dependency on NVIDIA tooling, so the same interface works for CPU,
CUDA, ROCm, Metal, and future local runtimes.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sidra_ai.models.base import (
    GenerationRequest,
    LocalModelAdapter,
    estimate_tokens,
)

MemoryProbe = Callable[[], float | None]
Clock = Callable[[], float]


class UnsafeBenchmarkBackendError(RuntimeError):
    """Raised if a benchmark target could incur per-token external cost."""


@dataclass(frozen=True)
class BenchmarkResult:
    """One local inference measurement with no prompt or generated text."""

    backend: str
    model: str
    quantization: str
    supports_streaming: bool
    input_tokens_estimate: int
    output_tokens_estimate: int
    time_to_first_token_s: float | None
    total_time_s: float
    output_tokens_per_second: float
    memory_before_mib: float | None = None
    memory_after_mib: float | None = None
    memory_delta_mib: float | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return only aggregate metrics; never retain prompt or output text."""

        return {
            "backend": self.backend,
            "model": self.model,
            "quantization": self.quantization,
            "supports_streaming": self.supports_streaming,
            "input_tokens_estimate": self.input_tokens_estimate,
            "output_tokens_estimate": self.output_tokens_estimate,
            "time_to_first_token_s": self.time_to_first_token_s,
            "total_time_s": self.total_time_s,
            "output_tokens_per_second": self.output_tokens_per_second,
            "memory_before_mib": self.memory_before_mib,
            "memory_after_mib": self.memory_after_mib,
            "memory_delta_mib": self.memory_delta_mib,
            "metadata": dict(self.metadata or {}),
            "external_api_cost_usd": 0.0,
        }


def _stream_token_estimate(cjk_chars: int, other_chars: int) -> int:
    """Match ``estimate_tokens`` without retaining streamed generated text."""

    if cjk_chars <= 0 and other_chars <= 0:
        return 0
    return cjk_chars + max(1, other_chars // 4)


def run_benchmark(
    adapter: LocalModelAdapter,
    request: GenerationRequest,
    *,
    memory_probe: MemoryProbe | None = None,
    clock: Clock = time.perf_counter,
) -> BenchmarkResult:
    """Measure one generation without coupling to a backend or GPU vendor.

    ``memory_probe`` should return *used* accelerator memory in MiB. It is
    called immediately before and after generation. A later hardware-specific
    probe may sample peak memory independently, but the core model lane stays
    dependency-free.

    Native streaming adapters expose time-to-first-token. For a non-streaming
    adapter that value equals total latency because the first token is not
    observable separately.

    Streaming output is never concatenated into a full in-memory answer merely
    for metrics. Character-class counters preserve the same fallback token
    estimate as :func:`estimate_tokens` while keeping the benchmark's memory
    overhead bounded as generation length grows.
    """

    if adapter.requires_paid_api:
        raise UnsafeBenchmarkBackendError(
            f"refusing to benchmark paid backend {adapter.backend!r}"
        )

    memory_before = memory_probe() if memory_probe is not None else None
    started = clock()
    first_token_at: float | None = None
    input_tokens = 0
    output_tokens = 0
    generated_any = False
    streamed_cjk_chars = 0
    streamed_other_chars = 0

    if adapter.supports_streaming:
        terminal_seen = False
        for chunk in adapter.generate_stream(request):
            if chunk.text_delta:
                generated_any = True
                if first_token_at is None:
                    first_token_at = clock()
                for char in chunk.text_delta:
                    if "　" <= char <= "鿿" or "＀" <= char <= "￯":
                        streamed_cjk_chars += 1
                    else:
                        streamed_other_chars += 1
            if chunk.input_tokens_estimate:
                input_tokens = chunk.input_tokens_estimate
            if chunk.output_tokens_estimate:
                output_tokens = chunk.output_tokens_estimate
            if chunk.done:
                terminal_seen = True
                break
        if not terminal_seen:
            # Native adapters should already enforce this. Keep the harness
            # fail-closed as defense in depth for future custom backends.
            raise RuntimeError("stream benchmark ended without a terminal event")
        if output_tokens <= 0 and generated_any:
            output_tokens = _stream_token_estimate(
                streamed_cjk_chars,
                streamed_other_chars,
            )
    else:
        result = adapter.generate(request)
        generated_any = bool(result.text)
        input_tokens = result.input_tokens_estimate
        output_tokens = result.output_tokens_estimate
        if output_tokens <= 0 and result.text:
            output_tokens = estimate_tokens(result.text)

    finished = clock()
    memory_after = memory_probe() if memory_probe is not None else None

    total_time = max(0.0, finished - started)
    if input_tokens <= 0:
        input_tokens = estimate_tokens(adapter.build_prompt(request))

    if adapter.supports_streaming:
        ttft = (
            max(0.0, first_token_at - started)
            if first_token_at is not None
            else None
        )
    else:
        ttft = total_time if generated_any else None

    throughput = output_tokens / total_time if total_time > 0 else 0.0
    memory_delta = (
        memory_after - memory_before
        if memory_before is not None and memory_after is not None
        else None
    )

    quantization = str(adapter.options.get("quantization") or "unknown")
    return BenchmarkResult(
        backend=adapter.backend,
        model=adapter.model,
        quantization=quantization,
        supports_streaming=adapter.supports_streaming,
        input_tokens_estimate=input_tokens,
        output_tokens_estimate=output_tokens,
        time_to_first_token_s=ttft,
        total_time_s=total_time,
        output_tokens_per_second=throughput,
        memory_before_mib=memory_before,
        memory_after_mib=memory_after,
        memory_delta_mib=memory_delta,
        metadata={"cost_usd": 0.0},
    )
