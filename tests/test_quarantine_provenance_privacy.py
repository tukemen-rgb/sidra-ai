from __future__ import annotations

import json
from datetime import datetime, timezone

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.security.decisions import Decision
from sidra_ai.security.gate import QuarantineStore, SecurityGate


def _provenance_with_sensitive_metadata() -> tuple[Provenance, tuple[str, ...]]:
    synthetic_secret = "ghp_" + "Q" * 24
    synthetic_pii = "private.person@example.com"
    provenance = Provenance(
        source="github",
        repository=f"owner/{synthetic_secret}",
        path=f"docs/{synthetic_pii}.md",
        commit_sha=synthetic_secret,
        timestamp=datetime(2026, 8, 17, tzinfo=timezone.utc),
        source_type=SourceType.DOCS,
        trust_level=TrustLevel.EXTERNAL,
        license=synthetic_pii,
        url=f"https://example.invalid/{synthetic_secret}",
        author=synthetic_pii,
        extra={"note": synthetic_secret, synthetic_pii: "value"},
    )
    sensitive_values = (
        synthetic_secret,
        synthetic_pii,
        provenance.repository,
        provenance.path,
        provenance.commit_sha,
        provenance.license,
        provenance.url,
        provenance.author,
    )
    return provenance, sensitive_values


def test_rejected_document_provenance_is_context_free_in_quarantine(tmp_path) -> None:
    provenance, sensitive_values = _provenance_with_sensitive_metadata()
    store = QuarantineStore(tmp_path / "quarantine.jsonl")
    gate = SecurityGate(
        allowed_repositories=("safe/repo",),
        quarantine_store=store,
    )

    result, screened = gate.screen_document(
        Document(content="benign body", provenance=provenance)
    )

    assert result.decision is Decision.BLOCK
    assert screened is None
    entry = store.entries()[0]
    audit_provenance = entry["provenance"]
    assert audit_provenance == {
        "source_type": SourceType.DOCS.value,
        "trust_level": TrustLevel.EXTERNAL.value,
        "timestamp": provenance.timestamp.isoformat(),
        "retrieved_at": provenance.retrieved_at.isoformat(),
        "source_length": len(provenance.source),
        "repository_length": len(provenance.repository),
        "path_length": len(provenance.path),
        "commit_sha_length": len(provenance.commit_sha),
        "license_length": len(provenance.license),
        "url_length": len(provenance.url),
        "author_length": len(provenance.author),
        "extra_count": len(provenance.extra),
    }

    serialized = json.dumps(entry, ensure_ascii=False)
    for sensitive in sensitive_values:
        assert sensitive not in serialized
    for raw_extra_key, raw_extra_value in provenance.extra.items():
        assert raw_extra_key not in serialized
        assert raw_extra_value not in serialized


def test_allowlisted_quarantine_keeps_normal_source_attribution(tmp_path) -> None:
    provenance = Provenance(
        source="github",
        repository="safe/repo",
        path="docs/review.md",
        commit_sha="a" * 40,
        timestamp=datetime(2026, 8, 17, tzinfo=timezone.utc),
        source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO,
        license="proprietary",
    )
    store = QuarantineStore(tmp_path / "quarantine.jsonl")
    gate = SecurityGate(
        allowed_repositories=("safe/repo",),
        quarantine_store=store,
    )
    synthetic_secret = "ghp_" + "Z" * 24

    result, screened = gate.screen_document(
        Document(content=f"token={synthetic_secret}", provenance=provenance)
    )

    assert result.decision is Decision.QUARANTINE
    assert screened is None
    entry = store.entries()[0]
    assert entry["provenance"] == provenance.to_dict()
    assert synthetic_secret not in json.dumps(entry, ensure_ascii=False)
