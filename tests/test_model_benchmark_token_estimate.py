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


def _class_counts(text: str) -> tuple[int, int, int]:
    cjk = 0
    ascii_chars = 0
    unicode_fallback_tokens = 0
    for char in text:
        if (
            "\u3000" <= char <= "\u9fff"
            or "\uac00" <= char <= "\ud7af"
            or "\uff00" <= char <= "\uffef"
        ):
            cjk += 1
        elif ord(char) < 128:
            ascii_chars += 1
        else:
            unicode_fallback_tokens += len(char.encode("utf-8"))
    return cjk, ascii_chars, unicode_fallback_tokens


@pytest.mark.parametrize(
    "text",
    [
        "",
        "abcd",
        "abcde",
        "abcdefgh",
        "abcdefghi",
        "日本abcde",
        "ＡＢabcde",
        "한글abcde",
        "🙂🙂",
        "e\u0301",
        "日本🙂abc",
    ],
)
def test_stream_fallback_estimate_matches_shared_token_heuristic(text: str) -> None:
    cjk, ascii_chars, unicode_fallback_tokens = _class_counts(text)
    assert (
        _stream_token_estimate(cjk, ascii_chars, unicode_fallback_tokens)
        == estimate_tokens(text)
    )


class _StreamingAdapter(LocalModelAdapter):
    backend = "test_stream"
    supports_streaming = True

    def __init__(self, chunks: tuple[str, ...] = ("abc", "de")) -> None:
        super().__init__("benchmark-fixture", quantization="test")
        self._chunks = chunks

    def generate(self, request: GenerationRequest) -> GenerationResult:
        raise AssertionError("streaming benchmark should not call generate()")

    def generate_stream(self, request: GenerationRequest) -> Iterator[GenerationChunk]:
        for index, text in enumerate(self._chunks):
            done = index == len(self._chunks) - 1
            yield GenerationChunk(
                text_delta=text,
                backend=self.backend,
                model=self.model,
                done=done,
                finish_reason="stop" if done else "",
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


def test_streaming_benchmark_keeps_unicode_estimate_conservative_across_chunks() -> None:
    ticks = iter([20.0, 20.1, 21.0])
    text = "🙂한🙂"
    result = run_benchmark(
        _StreamingAdapter(("🙂", "한🙂")),
        GenerationRequest(system_prompt="system", user_message="question"),
        clock=lambda: next(ticks),
    )

    assert result.output_tokens_estimate == estimate_tokens(text)
    assert result.output_tokens_estimate == 9
    assert result.output_tokens_per_second == pytest.approx(9.0)
    assert result.time_to_first_token_s == pytest.approx(0.1)
