"""Adapters for locally hosted inference servers.

Both Ollama and llama.cpp's ``llama-server`` speak HTTP on loopback. Neither
is imported at module load: ``httpx`` is only touched inside generation, so a
checkout without these servers still imports and tests cleanly.

Endpoints are validated as loopback by default. Pointing SIDRA at a remote
inference host is possible but must be deliberate - it turns prompts
(including retrieved internal content) into outbound network traffic.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

from sidra_ai.config.settings import LOCALHOST_ADDRESSES
from sidra_ai.models.base import (
    GenerationChunk,
    GenerationRequest,
    GenerationResult,
    LocalModelAdapter,
    ModelUnavailableError,
    estimate_tokens,
)


def _assert_local_endpoint(endpoint: str, *, allow_remote: bool) -> None:
    host = urlparse(endpoint).hostname or ""
    if host in LOCALHOST_ADDRESSES or allow_remote:
        return
    raise ModelUnavailableError(
        f"model endpoint host {host!r} is not loopback; set "
        "allow_remote_endpoint=true only if sending internal context to that "
        "host has been reviewed"
    )


class _HTTPAdapter(LocalModelAdapter):
    default_endpoint = ""
    timeout = 120.0

    def __init__(self, model: str, **options: Any) -> None:
        super().__init__(model, **options)
        self.endpoint = (
            str(options.get("endpoint") or "").rstrip("/") or self.default_endpoint
        )
        self.allow_remote_endpoint = bool(options.get("allow_remote_endpoint", False))
        _assert_local_endpoint(
            self.endpoint, allow_remote=self.allow_remote_endpoint
        )

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ModelUnavailableError(
                f"the {self.backend} backend needs httpx installed"
            ) from exc

        url = f"{self.endpoint}{path}"
        try:
            response = httpx.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - surfaced as one error type
            raise ModelUnavailableError(
                f"{self.backend} backend at {self.endpoint} is unreachable: {exc}"
            ) from exc

    def _stream_lines(
        self, path: str, payload: dict[str, Any]
    ) -> Iterator[str]:
        """Yield non-empty response lines without buffering the full answer."""

        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ModelUnavailableError(
                f"the {self.backend} backend needs httpx installed"
            ) from exc

        url = f"{self.endpoint}{path}"
        try:
            with httpx.stream(
                "POST", url, json=payload, timeout=self.timeout
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        yield line
        except Exception as exc:  # noqa: BLE001 - surfaced as one error type
            raise ModelUnavailableError(
                f"{self.backend} stream at {self.endpoint} failed: {exc}"
            ) from exc

    def health(self) -> dict[str, Any]:
        info = super().health()
        info["endpoint"] = self.endpoint
        try:
            import httpx

            response = httpx.get(self.endpoint, timeout=3.0)
            info["available"] = response.status_code < 500
        except Exception as exc:  # noqa: BLE001
            info["available"] = False
            info["error"] = str(exc)[:200]
        return info

    def _finish(
        self, request: GenerationRequest, text: str, raw: dict[str, Any]
    ) -> GenerationResult:
        return GenerationResult(
            text=text,
            backend=self.backend,
            model=self.model,
            input_tokens_estimate=int(
                raw.get("prompt_eval_count")
                or raw.get("tokens_evaluated")
                or estimate_tokens(self.build_prompt(request))
            ),
            output_tokens_estimate=int(
                raw.get("eval_count")
                or raw.get("tokens_predicted")
                or estimate_tokens(text)
            ),
            metadata={"endpoint": self.endpoint, "cost_usd": 0.0},
        )

    def _chunk(
        self,
        *,
        request: GenerationRequest,
        text_delta: str,
        done: bool,
        output_text: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        finish_reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> GenerationChunk:
        return GenerationChunk(
            text_delta=text_delta,
            backend=self.backend,
            model=self.model,
            done=done,
            input_tokens_estimate=(
                input_tokens
                or (estimate_tokens(self.build_prompt(request)) if done else 0)
            ),
            output_tokens_estimate=(
                output_tokens or (estimate_tokens(output_text) if output_text else 0)
            ),
            finish_reason=finish_reason if done else "",
            metadata={"endpoint": self.endpoint, "cost_usd": 0.0, **(metadata or {})},
        )


class OllamaAdapter(_HTTPAdapter):
    """Talks to a local Ollama daemon (``/api/generate``)."""

    backend = "ollama"
    default_endpoint = "http://127.0.0.1:11434"
    supports_streaming = True

    def _payload(
        self, request: GenerationRequest, *, stream: bool
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "system": request.system_prompt,
            "prompt": self._data_and_question(request),
            "stream": stream,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_output_tokens,
            },
        }

    def generate(self, request: GenerationRequest) -> GenerationResult:
        raw = self._post("/api/generate", self._payload(request, stream=False))
        return self._finish(request, str(raw.get("response", "")), raw)

    def generate_stream(self, request: GenerationRequest) -> Iterator[GenerationChunk]:
        collected: list[str] = []
        terminal_seen = False
        for line in self._stream_lines(
            "/api/generate", self._payload(request, stream=True)
        ):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ModelUnavailableError("ollama returned invalid stream JSON") from exc
            if raw.get("error"):
                raise ModelUnavailableError(f"ollama stream failed: {raw['error']}")

            delta = str(raw.get("response", ""))
            if delta:
                collected.append(delta)
            done = bool(raw.get("done"))
            terminal_seen = terminal_seen or done
            if not delta and not done:
                continue

            metadata = {}
            if done:
                for key in (
                    "total_duration",
                    "load_duration",
                    "prompt_eval_duration",
                    "eval_duration",
                ):
                    value = raw.get(key)
                    if isinstance(value, (int, float)):
                        metadata[key] = value
            yield self._chunk(
                request=request,
                text_delta=delta,
                done=done,
                output_text="".join(collected),
                input_tokens=int(raw.get("prompt_eval_count") or 0),
                output_tokens=int(raw.get("eval_count") or 0),
                finish_reason=str(raw.get("done_reason") or ("stop" if done else "")),
                metadata=metadata,
            )
            if done:
                break

        if not terminal_seen:
            raise ModelUnavailableError("ollama stream ended without a terminal event")

    @staticmethod
    def _data_and_question(request: GenerationRequest) -> str:
        # System instructions travel in the dedicated `system` field; the
        # prompt carries only DATA and the operator's question.
        parts = []
        if request.data_context.strip():
            parts.append(request.data_context.strip())
        parts.append(f"OPERATOR QUESTION:\n{request.user_message.strip()}")
        return "\n\n".join(parts)


class LlamaCppAdapter(_HTTPAdapter):
    """Talks to ``llama-server`` from llama.cpp (``/completion``)."""

    backend = "llama_cpp"
    default_endpoint = "http://127.0.0.1:8080"
    supports_streaming = True

    def _payload(
        self, request: GenerationRequest, *, stream: bool
    ) -> dict[str, Any]:
        return {
            "prompt": self.build_prompt(request),
            "n_predict": request.max_output_tokens,
            "temperature": request.temperature,
            "stream": stream,
        }

    def generate(self, request: GenerationRequest) -> GenerationResult:
        raw = self._post("/completion", self._payload(request, stream=False))
        return self._finish(request, str(raw.get("content", "")), raw)

    def generate_stream(self, request: GenerationRequest) -> Iterator[GenerationChunk]:
        collected: list[str] = []
        token_count = 0
        terminal_seen = False

        for raw_line in self._stream_lines(
            "/completion", self._payload(request, stream=True)
        ):
            line = raw_line.strip()
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if line == "[DONE]":
                terminal_seen = True
                yield self._chunk(
                    request=request,
                    text_delta="",
                    done=True,
                    output_text="".join(collected),
                    output_tokens=token_count,
                    finish_reason="stop",
                )
                break

            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ModelUnavailableError("llama.cpp returned invalid SSE JSON") from exc
            if raw.get("error"):
                raise ModelUnavailableError(f"llama.cpp stream failed: {raw['error']}")

            delta = str(raw.get("content", ""))
            if delta:
                collected.append(delta)
            tokens = raw.get("tokens")
            if isinstance(tokens, list):
                token_count += len(tokens)

            done = bool(raw.get("stop"))
            terminal_seen = terminal_seen or done
            if not delta and not done:
                continue
            yield self._chunk(
                request=request,
                text_delta=delta,
                done=done,
                output_text="".join(collected),
                output_tokens=token_count,
                finish_reason=str(
                    raw.get("stop_type") or raw.get("stop_reason") or ("stop" if done else "")
                ),
            )
            if done:
                break

        if not terminal_seen:
            raise ModelUnavailableError("llama.cpp stream ended without a terminal event")


class TransformersAdapter(LocalModelAdapter):
    """In-process ``transformers`` backend.

    Imported lazily: ``transformers`` and ``torch`` are heavy and are not
    dependencies of SIDRA AI v0.1. This is the path for running a 32B model
    on owned hardware later.
    """

    backend = "transformers"
    requires_paid_api = False

    def __init__(self, model: str, **options: Any) -> None:
        super().__init__(model, **options)
        self._pipeline: Any = None

    def _ensure_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        try:
            from transformers import pipeline  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ModelUnavailableError(
                "the transformers backend needs `pip install transformers torch`"
            ) from exc
        self._pipeline = pipeline("text-generation", model=self.model)
        return self._pipeline

    def generate(self, request: GenerationRequest) -> GenerationResult:
        generator = self._ensure_pipeline()
        prompt = self.build_prompt(request)
        try:
            output = generator(
                prompt,
                max_new_tokens=request.max_output_tokens,
                temperature=request.temperature,
                return_full_text=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise ModelUnavailableError(f"transformers generation failed: {exc}") from exc

        text = output[0]["generated_text"] if output else ""
        return GenerationResult(
            text=text,
            backend=self.backend,
            model=self.model,
            input_tokens_estimate=estimate_tokens(prompt),
            output_tokens_estimate=estimate_tokens(text),
            metadata={"cost_usd": 0.0},
        )

    def health(self) -> dict[str, Any]:
        info = super().health()
        info["loaded"] = self._pipeline is not None
        return info
