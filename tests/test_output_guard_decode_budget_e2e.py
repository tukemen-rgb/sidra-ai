"""E2E regression for OutputGuard decode-budget fail-closed behavior.

This test is intentionally stacked on the Security fix that turns reversible-
decode budget exhaustion into a refusal. It exercises the real SidraService
output boundary so a future service refactor cannot silently reintroduce the
fail-open path even if lower-level detector tests remain green.
"""

from __future__ import annotations

import base64
from tempfile import TemporaryDirectory

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.models.base import GenerationRequest, GenerationResult, LocalModelAdapter
from sidra_ai.security.output_guard import OutputGuard


def _fake_github_token() -> str:
    """Build a synthetic credential shape without embedding a live credential."""

    return "ghp_" + "0" * 36


def _safe_base64_candidate() -> str:
    """Low-entropy valid Base64 that should remain safe at the exact budget."""

    return base64.b64encode(b"a" * 24).decode("ascii")


class _FixedOutputModel(LocalModelAdapter):
    backend = "echo"

    def __init__(self, text: str) -> None:
        super().__init__("sidra-eval-decode-budget")
        self._text = text
        self.calls = 0

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        return GenerationResult(text=self._text, backend=self.backend, model=self.model)


def test_exact_base64_candidate_budget_remains_allowed() -> None:
    """The bound itself must not become an off-by-one false positive."""

    candidate = _safe_base64_candidate()
    content = " ".join([candidate] * 32)

    result = OutputGuard().scan(content)

    assert result.blocked is False
    assert result.content == content


def test_decode_candidate_budget_exhaustion_fails_closed_before_api_return() -> None:
    """A credential after 32 harmless decodes must never escape the service."""

    token = _fake_github_token()
    encoded_token = base64.b64encode(token.encode("utf-8")).decode("ascii")
    safe_candidate = _safe_base64_candidate()
    model_output = " ".join([safe_candidate] * 32 + [encoded_token])

    with TemporaryDirectory(prefix="sidra-eval-decode-budget-") as data_dir:
        model = _FixedOutputModel(model_output)
        service = SidraService(settings=Settings(data_dir=data_dir), model=model)

        response = service.chat("Summarize the indexed evidence.")

    assert model.calls == 1
    assert response.get("refused") is True
    assert response.get("reason") == "output security detector failed closed"
    assert token not in repr(response)
    assert encoded_token not in repr(response)
