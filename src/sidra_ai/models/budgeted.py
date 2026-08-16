"""Context-budget enforcement wrapper for local model adapters.

The wrapper keeps token budgeting backend-agnostic: callers can provide an
explicit context-window limit from a measured model manifest or the L4 router,
and every wrapped local backend receives a request that has already passed the
same fail-closed budget policy.

No model name or parameter count is used to guess context size. Input is never
silently truncated; only the requested output token budget may be clamped.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sidra_ai.models.base import (
    GenerationChunk,
    GenerationRequest,
    GenerationResult,
    LocalModelAdapter,
    estimate_tokens,
)
from sidra_ai.models.budget import TokenBudgetDecision, enforce_token_budget


class BudgetedLocalModelAdapter(LocalModelAdapter):
    """Apply one explicit context-window policy around any local adapter."""

    def __init__(
        self,
        inner: LocalModelAdapter,
        *,
        max_context_tokens: int,
        reserve_tokens: int = 128,
        min_output_tokens: int = 1,
    ) -> None:
        if inner.requires_paid_api:
            raise ValueError("cannot budget-wrap a paid model backend")

        super().__init__(inner.model, **inner.options)
        self.inner = inner
        self.backend = inner.backend
        self.requires_paid_api = inner.requires_paid_api
        self.supports_streaming = inner.supports_streaming
        self.max_context_tokens = int(max_context_tokens)
        self.reserve_tokens = int(reserve_tokens)
        self.min_output_tokens = int(min_output_tokens)

        # Validate static configuration immediately rather than failing only
        # after the first request reaches the model process.
        if self.max_context_tokens <= 0:
            raise ValueError("max_context_tokens must be positive")
        if self.reserve_tokens < 0:
            raise ValueError("reserve_tokens cannot be negative")
        if self.reserve_tokens >= self.max_context_tokens:
            raise ValueError("reserve_tokens must leave usable context")
        if self.min_output_tokens <= 0:
            raise ValueError("min_output_tokens must be positive")

    def budget(self, request: GenerationRequest) -> TokenBudgetDecision:
        """Return the deterministic budget decision without invoking a model."""

        # Use the inner adapter's exact prompt composition so Ollama,
        # llama.cpp, Transformers and Echo are all measured against the input
        # they would actually receive. The estimator is conservative/local and
        # can later be replaced by an exact tokenizer count at the router/API
        # boundary without changing this wrapper contract.
        input_tokens = estimate_tokens(self.inner.build_prompt(request))
        return enforce_token_budget(
            request,
            input_tokens=input_tokens,
            max_context_tokens=self.max_context_tokens,
            reserve_tokens=self.reserve_tokens,
            min_output_tokens=self.min_output_tokens,
        )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Budget first; invoke the wrapped backend only on an admissible request."""

        decision = self.budget(request)
        return self.inner.generate(decision.request)

    def generate_stream(self, request: GenerationRequest) -> Iterator[GenerationChunk]:
        """Apply the same budget before native or compatibility streaming."""

        decision = self.budget(request)
        yield from self.inner.generate_stream(decision.request)

    def health(self) -> dict[str, Any]:
        """Preserve backend health while exposing non-secret budget metadata."""

        info = dict(self.inner.health())
        info.update(
            {
                "context_budget_enforced": True,
                "max_context_tokens": self.max_context_tokens,
                "context_reserve_tokens": self.reserve_tokens,
            }
        )
        return info
