"""Adapters for locally hosted inference servers.

Both Ollama and llama.cpp's ``llama-server`` speak HTTP on loopback. Neither
is imported at module load: ``httpx`` is only touched inside
:meth:`generate`, so a checkout without these servers still imports and tests
cleanly.

Endpoints are validated as loopback by default. Pointing SIDRA at a remote
inference host is possible but must be deliberate - it turns prompts
(including retrieved internal content) into outbound network traffic.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from sidra_ai.config.settings import LOCALHOST_ADDRESSES
from sidra_ai.models.base import (
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


class OllamaAdapter(_HTTPAdapter):
    """Talks to a local Ollama daemon (``/api/generate``)."""

    backend = "ollama"
    default_endpoint = "http://127.0.0.1:11434"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        raw = self._post(
            "/api/generate",
            {
                "model": self.model,
                "system": request.system_prompt,
                "prompt": self._data_and_question(request),
                "stream": False,
                "options": {
                    "temperature": request.temperature,
                    "num_predict": request.max_output_tokens,
                },
            },
        )
        return self._finish(request, str(raw.get("response", "")), raw)

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

    def generate(self, request: GenerationRequest) -> GenerationResult:
        raw = self._post(
            "/completion",
            {
                "prompt": self.build_prompt(request),
                "n_predict": request.max_output_tokens,
                "temperature": request.temperature,
                "stream": False,
            },
        )
        return self._finish(request, str(raw.get("content", "")), raw)


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
