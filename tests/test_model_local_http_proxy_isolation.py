from __future__ import annotations

import json

import httpx

from sidra_ai.models.base import GenerationRequest
from sidra_ai.models.http_backends import OllamaAdapter


class _Response:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "response": "ok",
            "prompt_eval_count": 1,
            "eval_count": 1,
        }


class _StreamResponse(_Response):
    def __enter__(self) -> "_StreamResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def iter_lines(self):
        yield json.dumps(
            {
                "response": "ok",
                "done": True,
                "prompt_eval_count": 1,
                "eval_count": 1,
            }
        )


def _request() -> GenerationRequest:
    return GenerationRequest(
        system_prompt="system",
        user_message="question",
        max_output_tokens=8,
    )


def test_local_nonstreaming_generation_ignores_ambient_proxy(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_post(url: str, **kwargs):
        observed.update(kwargs)
        return _Response()

    monkeypatch.setenv("HTTP_PROXY", "http://192.0.2.10:8080")
    monkeypatch.setenv("ALL_PROXY", "http://192.0.2.11:8080")
    monkeypatch.setattr(httpx, "post", fake_post)

    result = OllamaAdapter("local-test").generate(_request())

    assert result.text == "ok"
    assert observed["trust_env"] is False


def test_local_streaming_generation_ignores_ambient_proxy(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_stream(method: str, url: str, **kwargs):
        observed["method"] = method
        observed.update(kwargs)
        return _StreamResponse()

    monkeypatch.setenv("HTTP_PROXY", "http://192.0.2.10:8080")
    monkeypatch.setenv("ALL_PROXY", "http://192.0.2.11:8080")
    monkeypatch.setattr(httpx, "stream", fake_stream)

    chunks = list(OllamaAdapter("local-test").generate_stream(_request()))

    assert chunks[-1].done is True
    assert observed["method"] == "POST"
    assert observed["trust_env"] is False


def test_local_health_probe_ignores_ambient_proxy(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_get(url: str, **kwargs):
        observed.update(kwargs)
        return _Response()

    monkeypatch.setenv("HTTP_PROXY", "http://192.0.2.10:8080")
    monkeypatch.setenv("ALL_PROXY", "http://192.0.2.11:8080")
    monkeypatch.setattr(httpx, "get", fake_get)

    health = OllamaAdapter("local-test").health()

    assert health["available"] is True
    assert observed["trust_env"] is False
