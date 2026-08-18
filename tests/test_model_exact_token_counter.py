"""Exact local token-count hooks for constrained context budgets."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from sidra_ai.models.base import (
    GenerationRequest,
    GenerationResult,
    LocalModelAdapter,
)
from sidra_ai.models.budget import ContextWindowExceededError
from sidra_ai.models.budgeted import BudgetedLocalModelAdapter
from sidra_ai.models.registry import create_adapter


class RecordingAdapter(LocalModelAdapter):
    backend = "recording"

    def __init__(self) -> None:
        super().__init__("local")
        self.calls = 0
        self.seen: GenerationRequest | None = None

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        self.seen = request
        return GenerationResult(text="ok", backend=self.backend, model=self.model)


def _emoji_request(*, max_output_tokens: int = 1) -> GenerationRequest:
    return GenerationRequest(
        system_prompt="s",
        user_message="😀😀😀😀",
        max_output_tokens=max_output_tokens,
    )


def test_default_counter_remains_conservative_for_unicode() -> None:
    inner = RecordingAdapter()
    adapter = BudgetedLocalModelAdapter(
        inner,
        max_context_tokens=16,
        reserve_tokens=1,
    )

    with pytest.raises(ContextWindowExceededError, match="reduce input"):
        adapter.generate(_emoji_request())

    assert inner.calls == 0
    assert adapter.uses_custom_input_token_counter is False


def test_verified_local_counter_can_reclaim_safe_context_headroom() -> None:
    inner = RecordingAdapter()
    counted_prompts: list[str] = []

    def exact_counter(prompt: str) -> int:
        counted_prompts.append(prompt)
        return 8

    adapter = BudgetedLocalModelAdapter(
        inner,
        max_context_tokens=16,
        reserve_tokens=1,
        input_token_counter=exact_counter,
    )
    request = _emoji_request(max_output_tokens=7)

    result = adapter.generate(request)

    assert result.text == "ok"
    assert inner.calls == 1
    assert inner.seen is not None
    assert inner.seen.max_output_tokens == 7
    assert counted_prompts == [inner.build_prompt(request)]
    assert adapter.uses_custom_input_token_counter is True
    assert adapter.health()["custom_input_token_counter"] is True


@pytest.mark.parametrize(
    "counter",
    [
        pytest.param(lambda _prompt: -1, id="negative"),
        pytest.param(lambda _prompt: 0, id="zero-non-empty"),
        pytest.param(lambda _prompt: True, id="bool"),
        pytest.param(lambda _prompt: 1.5, id="float"),
    ],
)
def test_invalid_custom_counter_fails_before_backend(
    counter: Callable[[str], object],
) -> None:
    inner = RecordingAdapter()
    adapter = BudgetedLocalModelAdapter(
        inner,
        max_context_tokens=64,
        reserve_tokens=1,
        input_token_counter=counter,  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="input_token_counter"):
        adapter.generate(_emoji_request())

    assert inner.calls == 0


def test_custom_counter_exception_fails_before_backend() -> None:
    inner = RecordingAdapter()

    def broken_counter(_prompt: str) -> int:
        raise RuntimeError("tokenizer unavailable")

    adapter = BudgetedLocalModelAdapter(
        inner,
        max_context_tokens=64,
        reserve_tokens=1,
        input_token_counter=broken_counter,
    )

    with pytest.raises(ValueError, match="input_token_counter failed"):
        adapter.generate(_emoji_request())

    assert inner.calls == 0


def test_registry_consumes_counter_only_with_context_budget() -> None:
    counter = lambda _prompt: 8

    with pytest.raises(ValueError, match="input_token_counter require"):
        create_adapter("echo", "local", input_token_counter=counter)

    adapter = create_adapter(
        "echo",
        "local",
        max_context_tokens=256,
        input_token_counter=counter,
    )

    assert isinstance(adapter, BudgetedLocalModelAdapter)
    assert adapter.uses_custom_input_token_counter is True
    assert adapter.budget(_emoji_request(max_output_tokens=7)).input_tokens == 8
