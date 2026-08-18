"""The model adapter interface.

SIDRA AI must not be coupled to any single inference stack. Everything above
this module talks to :class:`LocalModelAdapter`; swapping llama.cpp for
Ollama, or a 7B for a 32B, is a configuration change, not a code change.

Two properties are load-bearing for security:

* :meth:`LocalModelAdapter.generate` takes a *system* prompt and a *data
  context* separately. Retrieved content only ever arrives through the data
  context, already wrapped by :mod:`sidra_ai.security.data_envelope`.
* :attr:`LocalModelAdapter.requires_paid_api` lets the API refuse to start a
  backend that would bill per token. v0.1 has none.
"""

from __future__ import annotations

import abc
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any


class ModelUnavailableError(RuntimeError):
    """Raised when a backend is configured but cannot be reached."""


@dataclass(frozen=True)
class GenerationRequest:
    """One inference request.

    ``data_context`` is untrusted DATA already wrapped in an envelope.
    ``system_prompt`` is the only instruction authority.
    """

    system_prompt: str
    user_message: str
    data_context: str = ""
    max_output_tokens: int = 512
    temperature: float = 0.2
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationResult:
    text: str
    backend: str
    model: str
    input_tokens_estimate: int = 0
    output_tokens_estimate: int = 0
    finish_reason: str = "stop"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "backend": self.backend,
            "model": self.model,
            "input_tokens_estimate": self.input_tokens_estimate,
            "output_tokens_estimate": self.output_tokens_estimate,
            "finish_reason": self.finish_reason,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class GenerationChunk:
    """One incremental generation event.

    ``text_delta`` contains only newly generated text. Token estimates are
    cumulative when provided. A terminal event always has ``done=True`` so a
    caller never has to infer completion from a closed HTTP connection.
    """

    text_delta: str
    backend: str
    model: str
    done: bool = False
    input_tokens_estimate: int = 0
    output_tokens_estimate: int = 0
    finish_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text_delta": self.text_delta,
            "backend": self.backend,
            "model": self.model,
            "done": self.done,
            "input_tokens_estimate": self.input_tokens_estimate,
            "output_tokens_estimate": self.output_tokens_estimate,
            "finish_reason": self.finish_reason,
            "metadata": dict(self.metadata),
        }


def _is_cjk_like(char: str) -> bool:
    """Return whether one code point is safe to budget near one token each."""

    return (
        "　" <= char <= "鿿"
        or "가" <= char <= "힯"
        or "＀" <= char <= "￯"
    )


def estimate_tokens(text: str) -> int:
    """Conservative local token estimate for mixed-language context budgets.

    CJK/Hangul characters are budgeted near one token each and plain ASCII is
    approximated at four characters per token with partial groups rounded up.
    Other Unicode is deliberately more conservative: its UTF-8 byte length is
    used as a tokenizer-independent fallback instead of grouping four code
    points into one token. That avoids severe under-counts for emoji, combining
    marks, and other scripts when a 6 GiB-class route is admitted without an
    exact model tokenizer.

    This is a safety estimate, not tokenizer-exact billing/accounting. v0.1 has
    no paid-per-token model backend.
    """

    if not text:
        return 0

    cjk_like = 0
    ascii_chars = 0
    unicode_fallback_tokens = 0
    for char in text:
        if _is_cjk_like(char):
            cjk_like += 1
        elif ord(char) < 128:
            ascii_chars += 1
        else:
            unicode_fallback_tokens += len(char.encode("utf-8"))

    ascii_tokens = (ascii_chars + 3) // 4
    return cjk_like + ascii_tokens + unicode_fallback_tokens


class LocalModelAdapter(abc.ABC):
    """Base class every backend implements."""

    #: Stable identifier used in configuration, e.g. ``"ollama"``.
    backend: str = "abstract"

    #: ``True`` only for backends that bill per token. v0.1 forbids these.
    requires_paid_api: bool = False

    #: True only when the backend emits tokens incrementally without first
    #: materializing the complete answer. The base fallback remains usable.
    supports_streaming: bool = False

    def __init__(self, model: str, **options: Any) -> None:
        self.model = model
        self.options = options

    @abc.abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Run inference. Must raise :class:`ModelUnavailableError` on failure."""

    def generate_stream(self, request: GenerationRequest) -> Iterator[GenerationChunk]:
        """Yield generation events through a stable backend-agnostic interface.

        Backends without native streaming deliberately fall back to one final
        chunk. Callers can adopt streaming now without requiring every local
        inference stack to implement it at once.
        """

        result = self.generate(request)
        yield GenerationChunk(
            text_delta=result.text,
            backend=result.backend,
            model=result.model,
            done=True,
            input_tokens_estimate=result.input_tokens_estimate,
            output_tokens_estimate=result.output_tokens_estimate,
            finish_reason=result.finish_reason,
            metadata=dict(result.metadata),
        )

    def health(self) -> dict[str, Any]:
        """Report backend reachability without raising."""

        return {
            "backend": self.backend,
            "model": self.model,
            "available": True,
            "requires_paid_api": self.requires_paid_api,
            "supports_streaming": self.supports_streaming,
        }

    # ------------------------------------------------------------------
    def build_prompt(self, request: GenerationRequest) -> str:
        """Compose the final prompt with DATA kept below the instructions.

        Shared by every backend so the ordering - system instructions first,
        untrusted data second, operator question last - is identical
        regardless of which inference stack is running.
        """

        parts = [request.system_prompt.strip()]
        if request.data_context.strip():
            parts.append(request.data_context.strip())
        parts.append(f"OPERATOR QUESTION:\n{request.user_message.strip()}")
        return "\n\n".join(parts)
