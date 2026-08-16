"""Offline regressions for redaction fingerprint privacy.

These cases exercise the real SecurityGate + QuarantineStore boundary.  They
protect the distinction between high-entropy credential correlation (where a
short deterministic fingerprint is useful) and guessable secrets/PII (where
publishing that digest becomes an offline guessing oracle).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.security.decisions import Decision
from sidra_ai.security.gate import QuarantineStore, SecurityGate
from sidra_ai.security.redaction import fingerprint


def _inspect_with_audit(content: str) -> tuple[object, str]:
    """Run the real gate and return its result plus serialized audit surfaces."""

    with tempfile.TemporaryDirectory() as temp_dir:
        store = QuarantineStore(Path(temp_dir) / "quarantine.jsonl")
        gate = SecurityGate(quarantine_store=store)
        result = gate.inspect(content, source="operator")
        serialized = json.dumps(
            {"gate": result.to_dict(), "quarantine": store.entries()},
            ensure_ascii=False,
            sort_keys=True,
        )
    return result, serialized


def _low_entropy_assignment_case() -> EvalOutcome:
    secret = "123456"
    result, serialized = _inspect_with_audit(f"password={secret}")
    failures: list[str] = []

    if result.decision is not Decision.QUARANTINE:
        failures.append(f"expected quarantine, got {result.decision.value}")
    if secret in serialized:
        failures.append("guessable assigned secret survived into an audit surface")
    if fingerprint(secret) in serialized:
        failures.append("guessable assigned secret retained a deterministic fingerprint")
    if "[REDACTED:assigned_secret]" not in result.content:
        failures.append("assigned secret was not replaced by a fingerprint-free placeholder")

    return EvalOutcome(
        case_name="redaction_guessable_assignment_has_no_fingerprint",
        passed=not failures,
        detail=result.decision.value,
        failures=tuple(failures),
    )


def _basic_auth_case() -> EvalOutcome:
    secret = "abcd!"
    result, serialized = _inspect_with_audit(f"https://user:{secret}@example.test/path")
    failures: list[str] = []

    if result.decision is not Decision.QUARANTINE:
        failures.append(f"expected quarantine, got {result.decision.value}")
    if secret in serialized:
        failures.append("guessable Basic Auth password survived into an audit surface")
    if fingerprint(secret) in serialized:
        failures.append("guessable Basic Auth password retained a deterministic fingerprint")
    if "[REDACTED:basic_auth_url]" not in result.content:
        failures.append("Basic Auth password was not fingerprint-free after redaction")

    return EvalOutcome(
        case_name="redaction_guessable_basic_auth_has_no_fingerprint",
        passed=not failures,
        detail=result.decision.value,
        failures=tuple(failures),
    )


def _provider_credential_case() -> EvalOutcome:
    token = "ghp_" + "A" * 36
    result, serialized = _inspect_with_audit(f"credential: {token}")
    expected_fingerprint = fingerprint(token)
    failures: list[str] = []

    if result.decision is not Decision.QUARANTINE:
        failures.append(f"expected quarantine, got {result.decision.value}")
    if token in serialized:
        failures.append("provider-shaped credential survived into an audit surface")
    if expected_fingerprint not in result.content:
        failures.append("high-entropy provider credential lost its correlation fingerprint")

    return EvalOutcome(
        case_name="redaction_provider_secret_keeps_safe_correlation_fingerprint",
        passed=not failures,
        detail=result.decision.value,
        failures=tuple(failures),
    )


def run_redaction_privacy_suite() -> list[EvalOutcome]:
    """Return deterministic redaction-privacy regressions with no network/model use."""

    return [
        _low_entropy_assignment_case(),
        _basic_auth_case(),
        _provider_credential_case(),
    ]
