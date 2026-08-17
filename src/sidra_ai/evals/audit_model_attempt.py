"""Offline release-gate checks for truthful model-attempt audit history."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from sidra_ai.api.audit import ApiAuditLog
from sidra_ai.evals.cases import EvalOutcome


def _last_event(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8").splitlines()[-1])


def _backend_failure() -> dict[str, object]:
    return {
        "answer": "",
        "refused": True,
        "reason": "model backend unavailable",
        "security": {"decision": "allow"},
        "citations": [],
    }


def run_audit_model_attempt_suite() -> tuple[EvalOutcome, ...]:
    """Require audit history to distinguish failed generation from no generation."""

    outcomes: list[EvalOutcome] = []
    with tempfile.TemporaryDirectory(prefix="sidra-audit-attempt-eval-") as tmp:
        root = Path(tmp)

        chat_path = root / "chat.jsonl"
        ApiAuditLog(chat_path).record_response(
            operation="chat",
            input_chars=12,
            requested_repositories=("tukemen-rgb/sidra-ai",),
            response=_backend_failure(),
        )
        chat = _last_event(chat_path)
        chat_failures: list[str] = []
        if chat.get("outcome") != "refused":
            chat_failures.append("backend failure was not audited as refused")
        if chat.get("decision") != "allow":
            chat_failures.append("backend failure lost the input security decision")
        if chat.get("model_invoked") is not True:
            chat_failures.append("failed chat generation was rewritten as model not invoked")
        outcomes.append(
            EvalOutcome(
                case_name="api_audit_failed_chat_preserves_model_attempt",
                passed=not chat_failures,
                detail="failed chat generation audit checked",
                failures=tuple(chat_failures),
            )
        )

        analyze_path = root / "analyze.jsonl"
        ApiAuditLog(analyze_path).record_response(
            operation="github_analyze",
            input_chars=8,
            requested_repositories=("tukemen-rgb/sidra-ai",),
            response={
                "ingestion": {"changed": True},
                "inference_skipped": False,
                "analysis": _backend_failure(),
            },
        )
        analyze = _last_event(analyze_path)
        analyze_failures: list[str] = []
        if analyze.get("outcome") != "refused":
            analyze_failures.append("nested backend failure was not audited as refused")
        if analyze.get("decision") != "allow":
            analyze_failures.append("nested backend failure lost the input security decision")
        if analyze.get("model_invoked") is not True:
            analyze_failures.append("failed github analysis lost its model-attempt history")
        outcomes.append(
            EvalOutcome(
                case_name="api_audit_failed_analyze_preserves_model_attempt",
                passed=not analyze_failures,
                detail="failed github analysis audit checked",
                failures=tuple(analyze_failures),
            )
        )

        gate_path = root / "gate.jsonl"
        ApiAuditLog(gate_path).record_response(
            operation="chat",
            input_chars=4,
            requested_repositories=(),
            response={
                "answer": "",
                "refused": True,
                "reason": "blocked by security gate",
                "security": {"decision": "quarantine"},
                "citations": [],
            },
        )
        gate = _last_event(gate_path)
        gate_failures: list[str] = []
        if gate.get("outcome") != "refused":
            gate_failures.append("security refusal was not audited as refused")
        if gate.get("decision") != "quarantine":
            gate_failures.append("security refusal lost its gate decision")
        if gate.get("model_invoked") is not False:
            gate_failures.append("pre-model security refusal falsely claimed a model attempt")
        outcomes.append(
            EvalOutcome(
                case_name="api_audit_gate_refusal_does_not_invent_model_attempt",
                passed=not gate_failures,
                detail="pre-model refusal audit checked",
                failures=tuple(gate_failures),
            )
        )

    return tuple(outcomes)
