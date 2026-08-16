"""Streaming fallback token estimates must match the shared local heuristic."""

from __future__ import annotations

import json

import pytest

from sidra_ai.models.base import GenerationRequest, estimate_tokens
from sidra_ai.models.http_backends import LlamaCppAdapter, OllamaAdapter


def _request() -> GenerationRequest:
    return GenerationRequest(system_prompt="system", user_message="question")


def test_ollama_stream_fallback_rounds_partial_latin_group_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = OllamaAdapter("local-model")
    events = [
        json.dumps({"response": "abc", "done": False}),
        json.dumps({"response": "de", "done": False}),
        json.dumps({"response": "", "done": True, "done_reason": "stop"}),
    ]
    monkeypatch.setattr(adapter, "_stream_lines", lambda path, payload: iter(events))

    chunks = list(adapter.generate_stream(_request()))
    text_chunks = [chunk for chunk in chunks if chunk.text_delta]

    assert [chunk.output_tokens_estimate for chunk in text_chunks] == [
        estimate_tokens("abc"),
        estimate_tokens("abcde"),
    ]
    assert chunks[-1].output_tokens_estimate == estimate_tokens("abcde") == 2


def test_llama_cpp_stream_fallback_matches_mixed_text_estimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = LlamaCppAdapter("local-model")
    events = [
        'data: {"content":"日abc","stop":false}',
        'data: {"content":"de","stop":true,"stop_type":"eos"}',
    ]
    monkeypatch.setattr(adapter, "_stream_lines", lambda path, payload: iter(events))

    chunks = list(adapter.generate_stream(_request()))

    assert chunks[-1].done is True
    assert chunks[-1].output_tokens_estimate == estimate_tokens("日abcde") == 3
