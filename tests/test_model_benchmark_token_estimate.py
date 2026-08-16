from __future__ import annotations

from collections.abc import Iterator

import pytest

from sidra_ai.models.base import (
    GenerationChunk,
    GenerationRequest,
    GenerationResult,
    LocalModelAdapter,
    estimate_tokens,
)
from sidra_ai.models.benchmark import _stream_token_estimate, run_benchmark


def _class_counts(text: str) -> tuple[int, int]:
    cjk = sum(
        1
        for char in text
        if "\u3000" <= char <= "\u9fff" or "\uff00" <= char <= "\uffef"
    )
    return cjk, len(text) - cjk


@pytest.mark.parametrize(
    "text",
    ["", "abcd", "abcde", "abcdefgh", "abcdefghi", "日本abcde", "ＡＢabcde"],
)
def test_stream_fallback_estimate_matches_shared_token_heuristic(text: str) -> None:
    cjk, other = _class_counts(text)
    assert _stream_token_estimate(cjk, other) == estimate_tokens(text)


class _StreamingAdapter(LocalModelAdapter):
    backend = "test_stream"
    supports_streaming = True

    def __init__(self) -> None:
        super().__init__("benchmark-fixture", quantization="test")

    def generate(self, request: GenerationRequest) -> GenerationResult:
        raise AssertionError("streaming benchmark should not call generate()")

    def generate_stream(self, request: GenerationRequest) -> Iterator[GenerationChunk]:
        yield GenerationChunk(
            text_delta="abc",
            backend=self.backend,
            model=self.model,
        )
        yield GenerationChunk(
            text_delta="de",
            backend=self.backend,
            model=self.model,
            done=True,
            finish_reason="stop",
        )


def test_streaming_benchmark_rounds_partial_latin_group_up() -> None:
    ticks = iter([10.0, 10.2, 11.0])
    result = run_benchmark(
        _StreamingAdapter(),
        GenerationRequest(system_prompt="system", user_message="question"),
        clock=lambda: next(ticks),
    )

    assert result.output_tokens_estimate == 2
    assert result.output_tokens_per_second == pytest.approx(2.0)
    assert result.time_to_first_token_s == pytest.approx(0.2)
