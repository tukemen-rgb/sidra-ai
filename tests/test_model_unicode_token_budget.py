"""Conservative Unicode token-budget regressions for constrained local routes."""

from __future__ import annotations

import pytest

from sidra_ai.models.base import (
    GenerationRequest,
    GenerationResult,
    LocalModelAdapter,
    estimate_tokens,
)
from sidra_ai.models.budget import ContextWindowExceededError
from sidra_ai.models.budgeted import BudgetedLocalModelAdapter


def test_token_estimate_preserves_ascii_japanese_and_hangul_behavior() -> None:
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2
    assert estimate_tokens("日abcde") == 3
    assert estimate_tokens("안녕") == 2


def test_token_estimate_uses_conservative_utf8_fallback_for_other_unicode() -> None:
    # The previous heuristic counted four emoji code points as roughly one
    # token. A byte-based fallback is deliberately conservative when SIDRA has
    # no exact tokenizer available at the 6 GiB routing boundary.
    assert estimate_tokens("😀") == len("😀".encode("utf-8"))
    assert estimate_tokens("😀😀😀😀") == len("😀😀😀😀".encode("utf-8"))

    # ASCII remains grouped, while the non-ASCII code point is budgeted by its
    # UTF-8 bytes rather than being hidden inside a four-character group.
    assert estimate_tokens("café") == 3


def test_budget_rejects_emoji_heavy_prompt_before_backend_call() -> None:
    class RecordingAdapter(LocalModelAdapter):
        backend = "recording"

        def __init__(self) -> None:
            super().__init__("local")
            self.calls = 0

        def generate(self, request: GenerationRequest) -> GenerationResult:
            self.calls += 1
            return GenerationResult(text="unsafe", backend=self.backend, model=self.model)

    inner = RecordingAdapter()
    adapter = BudgetedLocalModelAdapter(
        inner,
        max_context_tokens=16,
        reserve_tokens=1,
    )

    with pytest.raises(ContextWindowExceededError, match="reduce input"):
        adapter.generate(
            GenerationRequest(
                system_prompt="s",
                user_message="😀😀😀😀",
                max_output_tokens=1,
            )
        )

    assert inner.calls == 0
