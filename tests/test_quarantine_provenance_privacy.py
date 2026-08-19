from __future__ import annotations

import json
from datetime import datetime, timezone

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.security.decisions import Decision
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate


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


def test_oversized_block_names_the_repository_it_already_allowlisted(tmp_path) -> None:
    """A size rejection is attributable; everything uninspected stays a length.

    The repository cleared the allowlist before the byte budget was even
    measured, so naming it discloses one of the operator's own configured
    entries and nothing else. Without it the durable record said only that
    something was refused for size, which no operator can act on.

    What must not follow it: path, URL, author, license, commit and extra are
    attacker-controlled and never passed through the detectors, so they are
    still lengths, and no body content is retained at all.
    """

    synthetic_secret = "ghp_" + "O" * 24
    synthetic_pii = "oversized.person@example.com"
    provenance = Provenance(
        source="github",
        repository="safe/repo",
        path=f"docs/{synthetic_pii}.md",
        commit_sha=synthetic_secret,
        timestamp=datetime(2026, 8, 18, tzinfo=timezone.utc),
        source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO,
        license=synthetic_pii,
        url=f"https://example.invalid/{synthetic_secret}",
        author=synthetic_pii,
        extra={"note": synthetic_secret, synthetic_pii: "value"},
    )
    raw_body = f"token={synthetic_secret}\ncontact={synthetic_pii}"
    store = QuarantineStore(tmp_path / "quarantine.jsonl")
    gate = SecurityGate(
        policy=GatePolicy(max_input_bytes=8),
        allowed_repositories=("safe/repo",),
        quarantine_store=store,
    )

    result, screened = gate.screen_document(Document(content=raw_body, provenance=provenance))

    assert result.decision is Decision.BLOCK
    assert screened is None
    entry = store.entries()[0]
    assert entry["content"] is None
    assert entry["content_retention"] == "metadata_only"
    audit_provenance = entry["provenance"]
    assert audit_provenance == {
        "source": "github",
        "repository": "safe/repo",
        "source_type": SourceType.DOCS.value,
        "trust_level": TrustLevel.INTERNAL_REPO.value,
        "timestamp": provenance.timestamp.isoformat(),
        "retrieved_at": provenance.retrieved_at.isoformat(),
        "path_length": len(provenance.path),
        "commit_sha_length": len(provenance.commit_sha),
        "license_length": len(provenance.license),
        "url_length": len(provenance.url),
        "author_length": len(provenance.author),
        "extra_count": len(provenance.extra),
    }

    serialized = json.dumps(entry, ensure_ascii=False)
    for sensitive in (
        synthetic_secret,
        synthetic_pii,
        provenance.path,
        provenance.commit_sha,
        provenance.license,
        provenance.url,
        provenance.author,
        raw_body,
    ):
        assert sensitive not in serialized
    for raw_extra_key, raw_extra_value in provenance.extra.items():
        assert raw_extra_key not in serialized
        assert raw_extra_value not in serialized


def test_allowlisted_quarantine_minimizes_uninspected_provenance(tmp_path) -> None:
    metadata_secret = "ghp_" + "M" * 24
    metadata_pii = "metadata.person@example.com"
    body_secret = "ghp_" + "Z" * 24
    provenance = Provenance(
        source="github",
        repository="safe/repo",
        path=f"docs/{metadata_pii}-{metadata_secret}.md",
        commit_sha=metadata_secret,
        timestamp=datetime(2026, 8, 17, tzinfo=timezone.utc),
        source_type=SourceType.DOCS,
        trust_level=TrustLevel.EXTERNAL,
        license=metadata_pii,
        url=f"https://example.invalid/{metadata_secret}",
        author=metadata_pii,
        extra={"note": metadata_secret, metadata_pii: "value"},
    )
    store = QuarantineStore(tmp_path / "quarantine.jsonl")
    gate = SecurityGate(
        allowed_repositories=("safe/repo",),
        quarantine_store=store,
    )

    result, screened = gate.screen_document(
        Document(content=f"token={body_secret}", provenance=provenance)
    )

    assert result.decision is Decision.QUARANTINE
    assert screened is None
    entry = store.entries()[0]
    assert entry["provenance"] == {
        "source": "github",
        "repository": "safe/repo",
        "source_type": SourceType.DOCS.value,
        "trust_level": TrustLevel.EXTERNAL.value,
        "timestamp": provenance.timestamp.isoformat(),
        "retrieved_at": provenance.retrieved_at.isoformat(),
        "path_length": len(provenance.path),
        "commit_sha_length": len(provenance.commit_sha),
        "license_length": len(provenance.license),
        "url_length": len(provenance.url),
        "author_length": len(provenance.author),
        "extra_count": len(provenance.extra),
    }
    assert entry["content_retention"] == "sanitized"
    assert isinstance(entry["content"], str)
    assert "[REDACTED:" in entry["content"]

    serialized = json.dumps(entry, ensure_ascii=False)
    for sensitive in (
        metadata_secret,
        metadata_pii,
        body_secret,
        provenance.path,
        provenance.commit_sha,
        provenance.license,
        provenance.url,
        provenance.author,
    ):
        assert sensitive not in serialized
    for raw_extra_key, raw_extra_value in provenance.extra.items():
        assert raw_extra_key not in serialized
        assert raw_extra_value not in serialized
