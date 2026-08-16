"""Regression coverage for nested /v1/github/analyze audit metadata."""

from __future__ import annotations

import json
from tempfile import TemporaryDirectory
from pathlib import Path

from sidra_ai.api.audit import ApiAuditLog


def _fake_github_token() -> str:
    return "ghp_" + "7" * 36


def test_github_analyze_audit_uses_nested_analysis_outcome() -> None:
    token = _fake_github_token()

    with TemporaryDirectory(prefix="sidra-audit-test-") as directory:
        path = Path(directory) / "audit.jsonl"
        audit = ApiAuditLog(path)
        audit.record_response(
            operation="github_analyze",
            input_chars=21,
            requested_repositories=("tukemen-rgb/site",),
            response={
                "inference_skipped": False,
                "analysis": {
                    "answer": token,
                    "refused": True,
                    "reason": "model output withheld by security guard",
                    "security": {"decision": "allow"},
                    "citations": [{"repository": "tukemen-rgb/site"}],
                    "model": {"backend": "echo", "name": "synthetic"},
                },
            },
        )

        raw = path.read_text(encoding="utf-8")
        assert token not in raw
        event = json.loads(raw)
        assert event["operation"] == "github_analyze"
        assert event["outcome"] == "refused"
        assert event["decision"] == "allow"
        assert event["model_invoked"] is True
        assert event["citation_repositories"] == ["tukemen-rgb/site"]
        assert event["repository_count"] == 1


def test_github_analyze_audit_keeps_no_inference_as_skipped() -> None:
    with TemporaryDirectory(prefix="sidra-audit-test-") as directory:
        path = Path(directory) / "audit.jsonl"
        audit = ApiAuditLog(path)
        audit.record_response(
            operation="github_analyze",
            input_chars=0,
            requested_repositories=("tukemen-rgb/site",),
            response={
                "inference_skipped": True,
                "analysis": None,
            },
        )

        event = json.loads(path.read_text(encoding="utf-8"))
        assert event["outcome"] == "skipped"
        assert event["decision"] == "unknown"
        assert event["model_invoked"] is False
        assert event["citation_repositories"] == []
