"""Runtime admission guard for routed llama.cpp servers.

SIDRA's 6 GiB-class routing policy admits one generation context using an
explicit context-token budget. Unlike Ollama, llama-server configures context
size and parallel slots at server startup rather than per completion request.
A routed adapter must therefore verify the live local server still matches the
assumptions used for VRAM admission before every generation.

The guard is model-agnostic. It never downloads weights, changes llama-server
properties, or permits a remote endpoint; it only reads the loopback `/props`
endpoint already exposed by llama-server.
"""

from __future__ import annotations

from collections.abc import Iterator
from threading import Lock
from typing import Any

from sidra_ai.models.base import (
    GenerationChunk,
    GenerationRequest,
    GenerationResult,
    LocalModelAdapter,
    ModelUnavailableError,
)


class LlamaCppRuntimeGuard(LocalModelAdapter):
    """Verify llama-server context/slot configuration before routed inference."""

    backend = "llama_cpp"
    requires_paid_api = False
    supports_streaming = True
    props_timeout_s = 3.0

    def __init__(
        self,
        inner: LocalModelAdapter,
        *,
        expected_context_tokens: int,
    ) -> None:
        if inner.backend != "llama_cpp":
            raise ValueError("llama.cpp runtime guard requires a llama_cpp adapter")
        if inner.requires_paid_api:
            raise ValueError("llama.cpp runtime guard cannot wrap a paid adapter")
        if expected_context_tokens <= 0:
            raise ValueError("expected_context_tokens must be positive")

        super().__init__(inner.model, **inner.options)
        self.inner = inner
        self.supports_streaming = inner.supports_streaming
        self.expected_context_tokens = int(expected_context_tokens)
        self._props_client: Any | None = None
        self._props_client_lock = Lock()

    def _get_props_client(self) -> Any:
        """Lazily create one proxy-isolated client for repeated `/props` checks."""

        client = self._props_client
        if client is not None:
            return client

        with self._props_client_lock:
            client = self._props_client
            if client is not None:
                return client
            try:
                import httpx

                client = httpx.Client(trust_env=False)
            except Exception as exc:  # noqa: BLE001 - normalize local runtime failures
                raise ModelUnavailableError(
                    "llama.cpp runtime properties are unavailable"
                ) from exc
            self._props_client = client
            return client

    def _fetch_props(self) -> dict[str, Any]:
        endpoint = getattr(self.inner, "endpoint", "")
        if not isinstance(endpoint, str) or not endpoint:
            raise ModelUnavailableError("llama.cpp runtime properties are unavailable")

        client = self._get_props_client()
        try:
            response = client.get(
                f"{endpoint}/props",
                timeout=self.props_timeout_s,
            )
            response.raise_for_status()
            props = response.json()
        except Exception as exc:  # noqa: BLE001 - normalize local runtime failures
            raise ModelUnavailableError("llama.cpp runtime properties are unavailable") from exc

        if not isinstance(props, dict):
            raise ModelUnavailableError("llama.cpp runtime properties are invalid")
        return props

    def _validate_runtime(self) -> None:
        props = self._fetch_props()
        generation_settings = props.get("default_generation_settings")
        if not isinstance(generation_settings, dict):
            raise ModelUnavailableError("llama.cpp runtime properties are invalid")

        n_ctx = generation_settings.get("n_ctx")
        total_slots = props.get("total_slots")
        if (
            isinstance(n_ctx, bool)
            or not isinstance(n_ctx, int)
            or n_ctx <= 0
            or isinstance(total_slots, bool)
            or not isinstance(total_slots, int)
            or total_slots <= 0
        ):
            raise ModelUnavailableError("llama.cpp runtime properties are invalid")

        if total_slots != 1:
            raise ModelUnavailableError(
                "llama.cpp routed runtime requires exactly one server slot"
            )
        if n_ctx != self.expected_context_tokens:
            raise ModelUnavailableError(
                "llama.cpp runtime context does not match routed context cap"
            )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self._validate_runtime()
        return self.inner.generate(request)

    def generate_stream(self, request: GenerationRequest) -> Iterator[GenerationChunk]:
        self._validate_runtime()
        yield from self.inner.generate_stream(request)

    def health(self) -> dict[str, Any]:
        info = dict(self.inner.health())
        info["runtime_context_guard"] = True
        info["expected_context_tokens"] = self.expected_context_tokens
        if not info.get("available", True):
            info["runtime_context_verified"] = False
            return info
        try:
            self._validate_runtime()
        except ModelUnavailableError:
            info["available"] = False
            info["runtime_context_verified"] = False
            info["error"] = "llama.cpp runtime configuration does not match routed admission"
        else:
            info["runtime_context_verified"] = True
        return info
