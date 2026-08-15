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


def estimate_tokens(text: str) -> int:
    """Rough token estimate that works for mixed Japanese/English text.

    CJK characters are close to one token each; Latin text is closer to four
    characters per token. Good enough for budgeting and logging - never used
    for billing, because v0.1 does not bill.
    """

    cjk = sum(
        1
        for char in text
        if "　" <= char <= "鿿" or "＀" <= char <= "￯"
    )
    other = len(text) - cjk
    return cjk + max(1, other // 4) if text else 0


class LocalModelAdapter(abc.ABC):
    """Base class every backend implements."""

    #: Stable identifier used in configuration, e.g. ``"ollama"``.
    backend: str = "abstract"

    #: ``True`` only for backends that bill per token. v0.1 forbids these.
    requires_paid_api: bool = False

    def __init__(self, model: str, **options: Any) -> None:
        self.model = model
        self.options = options

    @abc.abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Run inference. Must raise :class:`ModelUnavailableError` on failure."""

    def health(self) -> dict[str, Any]:
        """Report backend reachability without raising."""

        return {
            "backend": self.backend,
            "model": self.model,
            "available": True,
            "requires_paid_api": self.requires_paid_api,
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
