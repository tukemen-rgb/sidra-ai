"""Bound concurrent local generation on constrained hardware.

A 6 GiB-class route is admitted for one model context at a time.  Allowing two
requests to generate concurrently can allocate a second KV cache after routing
and invalidate the memory budget that admitted the model.  This wrapper keeps
that admission assumption true without depending on Ollama, llama.cpp, or a
specific quantization.

The guard is deliberately fail-fast rather than an unbounded queue: when one
generation is already in flight, a second request receives a local-model busy
error before touching the backend.  Streaming holds the guard for the whole
iterator lifetime and releases it even when the caller closes the stream early.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

from sidra_ai.models.base import (
    GenerationChunk,
    GenerationRequest,
    GenerationResult,
    LocalModelAdapter,
    ModelUnavailableError,
)


class ModelBusyError(ModelUnavailableError):
    """Raised when constrained local inference already has one active request."""


class SingleFlightLocalModelAdapter(LocalModelAdapter):
    """Allow at most one active generation through a local adapter.

    The wrapper is backend-agnostic and preserves the wrapped adapter's public
    model/backend/cost/streaming attributes.  It does not start threads, wait on
    a queue, or make network calls; it only prevents a second generation from
    entering the backend while the first one is active.
    """

    def __init__(self, inner: LocalModelAdapter) -> None:
        if inner.requires_paid_api:
            raise ValueError("cannot single-flight a paid model backend")

        super().__init__(inner.model, **inner.options)
        self.inner = inner
        self.backend = inner.backend
        self.requires_paid_api = inner.requires_paid_api
        self.supports_streaming = inner.supports_streaming
        self._generation_lock = threading.Lock()

        # Routing verifies this attribute when a context budget admitted the
        # adapter.  Preserve it exactly if the inner adapter exposes one.
        if hasattr(inner, "max_context_tokens"):
            self.max_context_tokens = getattr(inner, "max_context_tokens")

    def _acquire(self) -> None:
        if not self._generation_lock.acquire(blocking=False):
            raise ModelBusyError("local model already has an in-flight generation")

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self._acquire()
        try:
            return self.inner.generate(request)
        finally:
            self._generation_lock.release()

    def generate_stream(self, request: GenerationRequest) -> Iterator[GenerationChunk]:
        self._acquire()
        try:
            yield from self.inner.generate_stream(request)
        finally:
            # Generator.close(), backend failure, and normal completion all
            # release the same admission slot.
            self._generation_lock.release()

    def health(self) -> dict[str, Any]:
        info = dict(self.inner.health())
        info["single_flight_generation"] = True
        return info
