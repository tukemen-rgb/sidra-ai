"""Backend-agnostic context-window budgeting for local inference.

The model lane must not guess a model's context window from its name or
parameter count. Callers provide a measured or manifest-declared context
limit and an input-token estimate (or exact tokenizer count when available).

This module deliberately does not truncate system instructions, operator
questions, or retrieved DATA. If the input already leaves too little room for
generation it fails closed and reports how much input must be removed by the
caller/retrieval layer. When only the requested output is too large, it safely
clamps ``max_output_tokens`` while preserving the original request fields.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from sidra_ai.models.base import GenerationRequest


class ContextWindowExceededError(ValueError):
    """Raised when input leaves no safe room for the minimum output budget."""

    def __init__(
        self,
        *,
        input_tokens: int,
        max_context_tokens: int,
        reserve_tokens: int,
        min_output_tokens: int,
    ) -> None:
        self.input_tokens = input_tokens
        self.max_context_tokens = max_context_tokens
        self.reserve_tokens = reserve_tokens
        self.min_output_tokens = min_output_tokens

        usable = max_context_tokens - reserve_tokens
        self.required_reduction_tokens = max(
            0, input_tokens + min_output_tokens - usable
        )
        super().__init__(
            "input context leaves insufficient room for safe generation; "
            f"reduce input by at least {self.required_reduction_tokens} tokens"
        )


@dataclass(frozen=True)
class TokenBudgetDecision:
    """Result of fitting one request inside a declared model context window."""

    request: GenerationRequest
    input_tokens: int
    max_context_tokens: int
    reserve_tokens: int
    requested_output_tokens: int
    allowed_output_tokens: int
    clamped: bool

    @property
    def total_budget_tokens(self) -> int:
        """Worst-case input + allowed output + reserved headroom."""

        return self.input_tokens + self.allowed_output_tokens + self.reserve_tokens


def enforce_token_budget(
    request: GenerationRequest,
    *,
    input_tokens: int,
    max_context_tokens: int,
    reserve_tokens: int = 128,
    min_output_tokens: int = 1,
) -> TokenBudgetDecision:
    """Fit ``request`` into an explicitly declared local-model context window.

    ``input_tokens`` may be an exact tokenizer count or a conservative local
    estimate. ``max_context_tokens`` must come from a benchmark/model manifest;
    this function never infers it from a model name.

    Input is never silently truncated because dropping system instructions or
    evidence can change safety/correctness semantics. Instead, an oversized
    input raises :class:`ContextWindowExceededError` with the minimum reduction
    required. Only the output budget may be reduced automatically.
    """

    if input_tokens < 0:
        raise ValueError("input_tokens cannot be negative")
    if max_context_tokens <= 0:
        raise ValueError("max_context_tokens must be positive")
    if reserve_tokens < 0:
        raise ValueError("reserve_tokens cannot be negative")
    if reserve_tokens >= max_context_tokens:
        raise ValueError("reserve_tokens must leave usable context")
    if min_output_tokens <= 0:
        raise ValueError("min_output_tokens must be positive")
    if request.max_output_tokens <= 0:
        raise ValueError("request.max_output_tokens must be positive")

    usable_context = max_context_tokens - reserve_tokens
    available_output = usable_context - input_tokens
    if available_output < min_output_tokens:
        raise ContextWindowExceededError(
            input_tokens=input_tokens,
            max_context_tokens=max_context_tokens,
            reserve_tokens=reserve_tokens,
            min_output_tokens=min_output_tokens,
        )

    allowed_output = min(request.max_output_tokens, available_output)
    prepared = replace(request, max_output_tokens=allowed_output)
    return TokenBudgetDecision(
        request=prepared,
        input_tokens=input_tokens,
        max_context_tokens=max_context_tokens,
        reserve_tokens=reserve_tokens,
        requested_output_tokens=request.max_output_tokens,
        allowed_output_tokens=allowed_output,
        clamped=allowed_output != request.max_output_tokens,
    )
