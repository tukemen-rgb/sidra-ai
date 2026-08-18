from __future__ import annotations

import json
from pathlib import Path

import pytest

from sidra_ai.api.audit import ApiAuditLog


def _record_retrieve_with_repository(path: Path, repository: str) -> str:
    audit = ApiAuditLog(path)
    audit.record_response(
        operation="retrieve",
        input_chars=4,
        requested_repositories=(repository,),
        response={
            "refused": False,
            "security": {"decision": "allow"},
            "results": [{"citation": {"repository": repository}}],
        },
    )
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "repository,sensitive_value",
    [
        (
            "owner/ghp_" + "7" * 36,
            "ghp_" + "7" * 36,
        ),
        (
            "owner/person@example.com",
            "person@example.com",
        ),
    ],
)
def test_audit_redacts_secret_or_pii_in_repository_metadata(
    tmp_path: Path, repository: str, sensitive_value: str
) -> None:
    path = tmp_path / "audit.jsonl"

    raw = _record_retrieve_with_repository(path, repository)

    assert sensitive_value not in raw
    assert repository not in raw
    event = json.loads(raw)
    assert event["citation_repositories"] == ["<redacted-repository>"]
    assert event["repository_count"] == 1
    assert "fingerprint" not in raw.lower()


def test_audit_preserves_benign_repository_metadata(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"

    raw = _record_retrieve_with_repository(path, "tukemen-rgb/site")

    event = json.loads(raw)
    assert event["citation_repositories"] == ["tukemen-rgb/site"]
    assert event["repository_count"] == 1
