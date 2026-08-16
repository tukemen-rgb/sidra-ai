from __future__ import annotations

import json
from pathlib import Path

from sidra_ai.api.audit import ApiAuditLog


def _last_event(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8").splitlines()[-1])


def _failed_model_response() -> dict[str, object]:
    return {
        "answer": "",
        "refused": True,
        "reason": "model backend unavailable",
        "security": {"decision": "allow"},
        "citations": [],
    }


def test_chat_audit_records_backend_failure_as_model_attempt(tmp_path: Path) -> None:
    path = tmp_path / "api_audit.jsonl"
    audit = ApiAuditLog(path)

    audit.record_response(
        operation="chat",
        input_chars=12,
        requested_repositories=("tukemen-rgb/sidra-ai",),
        response=_failed_model_response(),
    )

    event = _last_event(path)
    assert event["outcome"] == "refused"
    assert event["decision"] == "allow"
    assert event["model_invoked"] is True
    assert event["repository_count"] == 1


def test_github_analyze_audit_records_nested_backend_failure_as_model_attempt(
    tmp_path: Path,
) -> None:
    path = tmp_path / "api_audit.jsonl"
    audit = ApiAuditLog(path)

    audit.record_response(
        operation="github_analyze",
        input_chars=8,
        requested_repositories=("tukemen-rgb/sidra-ai",),
        response={
            "ingestion": {"changed": True},
            "inference_skipped": False,
            "analysis": _failed_model_response(),
        },
    )

    event = _last_event(path)
    assert event["outcome"] == "refused"
    assert event["decision"] == "allow"
    assert event["model_invoked"] is True


def test_non_model_refusal_does_not_claim_model_attempt(tmp_path: Path) -> None:
    path = tmp_path / "api_audit.jsonl"
    audit = ApiAuditLog(path)

    audit.record_response(
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

    event = _last_event(path)
    assert event["outcome"] == "refused"
    assert event["model_invoked"] is False
