"""Offline release gate for local-model ambient proxy isolation.

SIDRA's Ollama and llama.cpp adapters are loopback-only capability boundaries.
This eval proves that generation, streaming generation, and health probes share
one local HTTP client without trusting ambient HTTP proxy environment variables.
No socket or model is started.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import httpx

from sidra_ai.evals.cases import EvalOutcome
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


def _loopback_http_ignores_ambient_proxies() -> EvalOutcome:
    failures: list[str] = []
    observed: dict[str, dict[str, object]] = {}
    created_clients = 0

    class _Client:
        def post(self, url: str, **kwargs):
            observed["post"] = {"url": url, **kwargs}
            return _Response()

        def stream(self, method: str, url: str, **kwargs):
            observed["stream"] = {"method": method, "url": url, **kwargs}
            return _StreamResponse()

        def get(self, url: str, **kwargs):
            observed["get"] = {"url": url, **kwargs}
            return _Response()

    def fake_client(**kwargs):
        nonlocal created_clients
        created_clients += 1
        observed["client"] = dict(kwargs)
        return _Client()

    proxy_env = {
        "HTTP_PROXY": "http://192.0.2.10:8080",
        "HTTPS_PROXY": "http://192.0.2.11:8080",
        "ALL_PROXY": "http://192.0.2.12:8080",
        "NO_PROXY": "",
    }

    with (
        patch.dict(os.environ, proxy_env, clear=False),
        patch.object(httpx, "Client", side_effect=fake_client),
    ):
        adapter = OllamaAdapter("local-eval")
        generated = adapter.generate(_request())
        chunks = list(adapter.generate_stream(_request()))
        health = adapter.health()

    if generated.text != "ok":
        failures.append("non-streaming local generation did not complete")
    if not chunks or not chunks[-1].done:
        failures.append("streaming local generation did not reach a terminal event")
    if health.get("available") is not True:
        failures.append("local health probe did not complete")
    if created_clients != 1:
        failures.append("local HTTP paths did not reuse exactly one adapter client")

    client_options = observed.get("client")
    if client_options is None:
        failures.append("local HTTP client was not initialized")
    elif client_options.get("trust_env") is not False:
        failures.append("local HTTP client did not set trust_env=False")

    for name in ("post", "stream", "get"):
        call = observed.get(name)
        if call is None:
            failures.append(f"expected local HTTP {name} path was not exercised")
            continue
        url = str(call.get("url", ""))
        if not url.startswith("http://127.0.0.1:11434"):
            failures.append(f"local HTTP {name} path did not remain on loopback")

    return EvalOutcome(
        case_name="local_model_http_ignores_ambient_proxies",
        passed=not failures,
        detail="local inference HTTP must reuse one proxy-isolated loopback client",
        failures=tuple(failures),
    )


def run_local_proxy_isolation_suite() -> list[EvalOutcome]:
    """Run the loopback inference proxy-isolation release gate offline."""

    return [_loopback_http_ignores_ambient_proxies()]
