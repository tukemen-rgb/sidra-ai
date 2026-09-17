"""C-1909: a benign question with an invisible character is not gate-refused.

A zero-width space from a web paste, the ZWJ that welds an emoji like 👨‍💻, a
BOM off a copied file - each turned an ordinary question into
``refused=True refusal="gate"``. The fix strips invisible characters from the
operator message before the gate sees it. Because stripping only *reveals*
hidden text, an obfuscated injection stays caught (guardrail), and the
``source="github"`` ingestion contract is untouched (scope).
"""

from __future__ import annotations

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.chat_operator_invisible_chars_do_not_false_refuse import (
    BENIGN_WITH_INVISIBLE,
    OBFUSCATED_INJECTIONS,
    PLAIN_INJECTION,
    evaluate_chat_operator_invisible_chars_do_not_false_refuse,
)
from sidra_ai.ingestion.state import StateStore
from sidra_ai.security.detectors import PromptInjectionDetector


@pytest.fixture()
def service(tmp_path) -> SidraService:
    return SidraService(
        Settings(data_dir=str(tmp_path), model_backend="echo"),
        state_store=StateStore(tmp_path / "state.json"),
    )


def test_eval_passes():
    result = evaluate_chat_operator_invisible_chars_do_not_false_refuse()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


@pytest.mark.parametrize("message", BENIGN_WITH_INVISIBLE)
def test_benign_with_invisible_char_is_not_gate_refused(service, message):
    assert service.chat(message).get("refusal") != "gate"


@pytest.mark.parametrize("message", OBFUSCATED_INJECTIONS)
def test_obfuscated_injection_still_refused(service, message):
    r = service.chat(message)
    assert r["refused"] is True
    assert r["refusal"] == "gate"


def test_plain_injection_still_refused(service):
    r = service.chat(PLAIN_INJECTION)
    assert r["refused"] is True
    assert r["refusal"] == "gate"


def test_ingestion_still_flags_invisible_chars():
    # The github ingestion contract is deliberately untouched by the fix: the
    # detector must still flag invisible characters on the ingestion path.
    detected = PromptInjectionDetector().detect("docs say: ​hidden")
    assert any(f.detector == "invisible_characters" for f in detected.findings)
