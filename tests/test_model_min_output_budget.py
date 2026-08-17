from __future__ import annotations

import pytest

from sidra_ai.models.base import GenerationRequest, GenerationResult, LocalModelAdapter
from sidra_ai.models.budget import enforce_token_budget
from sidra_ai.models.budgeted import BudgetedLocalModelAdapter


class RecordingAdapter(LocalModelAdapter):
    backend = "recording"

    def __init__(self) -> None:
        super().__init__("local")
        self.calls = 0

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        return GenerationResult(text="ok", backend=self.backend, model=self.model)


def test_budget_rejects_request_smaller_than_declared_minimum() -> None:
    request = GenerationRequest(
        system_prompt="system",
        user_message="question",
        max_output_tokens=8,
    )

    with pytest.raises(ValueError, match="smaller than min_output_tokens"):
        enforce_token_budget(
            request,
            input_tokens=32,
            max_context_tokens=4096,
            reserve_tokens=128,
            min_output_tokens=16,
        )


def test_budget_wrapper_refuses_before_backend_when_minimum_cannot_be_honored() -> None:
    inner = RecordingAdapter()
    adapter = BudgetedLocalModelAdapter(
        inner,
        max_context_tokens=4096,
        reserve_tokens=128,
        min_output_tokens=16,
    )

    with pytest.raises(ValueError, match="smaller than min_output_tokens"):
        adapter.generate(
            GenerationRequest(
                system_prompt="system",
                user_message="question",
                max_output_tokens=8,
            )
        )

    assert inner.calls == 0


def test_budget_accepts_request_exactly_at_declared_minimum() -> None:
    decision = enforce_token_budget(
        GenerationRequest(
            system_prompt="system",
            user_message="question",
            max_output_tokens=16,
        ),
        input_tokens=32,
        max_context_tokens=4096,
        reserve_tokens=128,
        min_output_tokens=16,
    )

    assert decision.allowed_output_tokens == 16
    assert decision.request.max_output_tokens == 16
