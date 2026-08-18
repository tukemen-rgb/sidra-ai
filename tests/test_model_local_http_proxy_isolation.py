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


class _FakeClient:
    def __init__(self, observed: dict[str, object]) -> None:
        self.observed = observed

    def post(self, url: str, **kwargs):
        self.observed["post"] = {"url": url, **kwargs}
        return _Response()

    def stream(self, method: str, url: str, **kwargs):
        self.observed["stream"] = {"method": method, "url": url, **kwargs}
        return _StreamResponse()

    def get(self, url: str, **kwargs):
        self.observed["get"] = {"url": url, **kwargs}
        return _Response()


def _request() -> GenerationRequest:
    return GenerationRequest(
        system_prompt="system",
        user_message="question",
        max_output_tokens=8,
    )


def _install_fake_client(monkeypatch, observed: dict[str, object]) -> None:
    def fake_client(**kwargs):
        observed["client"] = dict(kwargs)
        return _FakeClient(observed)

    monkeypatch.setattr(httpx, "Client", fake_client)


def test_local_nonstreaming_generation_ignores_ambient_proxy(monkeypatch) -> None:
    observed: dict[str, object] = {}
    monkeypatch.setenv("HTTP_PROXY", "http://192.0.2.10:8080")
    monkeypatch.setenv("ALL_PROXY", "http://192.0.2.11:8080")
    _install_fake_client(monkeypatch, observed)

    result = OllamaAdapter("local-test").generate(_request())

    assert result.text == "ok"
    client_options = observed["client"]
    assert isinstance(client_options, dict)
    assert client_options["trust_env"] is False


def test_local_streaming_generation_ignores_ambient_proxy(monkeypatch) -> None:
    observed: dict[str, object] = {}
    monkeypatch.setenv("HTTP_PROXY", "http://192.0.2.10:8080")
    monkeypatch.setenv("ALL_PROXY", "http://192.0.2.11:8080")
    _install_fake_client(monkeypatch, observed)

    chunks = list(OllamaAdapter("local-test").generate_stream(_request()))

    assert chunks[-1].done is True
    client_options = observed["client"]
    stream_call = observed["stream"]
    assert isinstance(client_options, dict)
    assert isinstance(stream_call, dict)
    assert client_options["trust_env"] is False
    assert stream_call["method"] == "POST"


def test_local_health_probe_ignores_ambient_proxy(monkeypatch) -> None:
    observed: dict[str, object] = {}
    monkeypatch.setenv("HTTP_PROXY", "http://192.0.2.10:8080")
    monkeypatch.setenv("ALL_PROXY", "http://192.0.2.11:8080")
    _install_fake_client(monkeypatch, observed)

    health = OllamaAdapter("local-test").health()

    assert health["available"] is True
    client_options = observed["client"]
    assert isinstance(client_options, dict)
    assert client_options["trust_env"] is False


def test_local_http_paths_reuse_one_proxy_isolated_client(monkeypatch) -> None:
    observed: dict[str, object] = {}
    created_clients = 0

    def fake_client(**kwargs):
        nonlocal created_clients
        created_clients += 1
        observed["client"] = dict(kwargs)
        return _FakeClient(observed)

    monkeypatch.setattr(httpx, "Client", fake_client)
    adapter = OllamaAdapter("local-test")

    assert adapter.generate(_request()).text == "ok"
    assert adapter.generate(_request()).text == "ok"
    assert list(adapter.generate_stream(_request()))[-1].done is True
    assert adapter.health()["available"] is True

    assert created_clients == 1
    client_options = observed["client"]
    post_call = observed["post"]
    stream_call = observed["stream"]
    health_call = observed["get"]
    assert isinstance(client_options, dict)
    assert isinstance(post_call, dict)
    assert isinstance(stream_call, dict)
    assert isinstance(health_call, dict)
    assert client_options["trust_env"] is False
    assert str(post_call["url"]).startswith("http://127.0.0.1:11434")
    assert str(stream_call["url"]).startswith("http://127.0.0.1:11434")
    assert str(health_call["url"]).startswith("http://127.0.0.1:11434")
