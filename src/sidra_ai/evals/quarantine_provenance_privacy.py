"""Offline release gate for quarantine provenance privacy.

Source allowlist and oversized-input rejection both short-circuit secret/PII
inspection by design. This suite proves that attacker-controlled provenance and
body content still cannot be persisted through the quarantine audit boundary,
while allowlisted quarantines retain only a repository-level review anchor.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from tempfile import TemporaryDirectory

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.security.decisions import Decision
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate


def _rejected_provenance_privacy() -> EvalOutcome:
    failures: list[str] = []
    synthetic_secret = "ghp_" + ("R" * 24)
    synthetic_pii = "private.person@example.com"
    rejected_repository = f"owner/{synthetic_secret}"

    provenance = Provenance(
        source="github",
        repository=rejected_repository,
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
    raw_body = f"token={synthetic_secret}\ncontact={synthetic_pii}"

    with TemporaryDirectory() as data_dir:
        store = QuarantineStore(f"{data_dir}/quarantine.jsonl")
        gate = SecurityGate(
            allowed_repositories=("safe/repo",),
            quarantine_store=store,
        )
        result, screened = gate.screen_document(
            Document(content=raw_body, provenance=provenance)
        )
        entries = store.entries()

    if result.decision is not Decision.BLOCK:
        failures.append(f"expected BLOCK, got {result.decision.value}")
    if screened is not None:
        failures.append("blocked unpermitted document became indexable")
    if len(entries) != 1:
        failures.append(f"expected one quarantine audit record, got {len(entries)}")
    else:
        entry = entries[0]
        if entry.get("content") is not None:
            failures.append("BLOCK audit persisted body content before secret/PII inspection")
        audit_provenance = entry.get("provenance")
        if not isinstance(audit_provenance, dict):
            failures.append("BLOCK audit omitted context-free provenance metadata")
        else:
            expected_keys = {
                "source_type",
                "trust_level",
                "timestamp",
                "retrieved_at",
                "source_length",
                "repository_length",
                "path_length",
                "commit_sha_length",
                "license_length",
                "url_length",
                "author_length",
                "extra_count",
            }
            if set(audit_provenance) != expected_keys:
                failures.append("rejected provenance audit retained unexpected fields")

        serialized = json.dumps(entry, ensure_ascii=False)
        forbidden = (
            synthetic_secret,
            synthetic_pii,
            rejected_repository,
            provenance.path,
            provenance.commit_sha,
            provenance.license,
            provenance.url,
            provenance.author,
            raw_body,
        )
        if any(value in serialized for value in forbidden):
            failures.append("rejected provenance/body data leaked into quarantine JSONL")
        if any(
            str(key) in serialized or str(value) in serialized
            for key, value in provenance.extra.items()
        ):
            failures.append("rejected provenance extra data leaked into quarantine JSONL")

    return EvalOutcome(
        case_name="security_rejected_provenance_quarantine_privacy",
        passed=not failures,
        detail="unpermitted source audit must be context-free and metadata-only",
        failures=tuple(failures),
    )


def _oversized_block_provenance_privacy() -> EvalOutcome:
    failures: list[str] = []
    synthetic_secret = "ghp_" + ("O" * 24)
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

    with TemporaryDirectory() as data_dir:
        store = QuarantineStore(f"{data_dir}/quarantine.jsonl")
        gate = SecurityGate(
            policy=GatePolicy(max_input_bytes=8),
            allowed_repositories=("safe/repo",),
            quarantine_store=store,
        )
        result, screened = gate.screen_document(
            Document(content=raw_body, provenance=provenance)
        )
        entries = store.entries()

    if result.decision is not Decision.BLOCK:
        failures.append(f"expected oversized BLOCK, got {result.decision.value}")
    if screened is not None:
        failures.append("oversized blocked document became indexable")
    if len(entries) != 1:
        failures.append(f"expected one oversized quarantine audit record, got {len(entries)}")
    else:
        entry = entries[0]
        if entry.get("content") is not None:
            failures.append("oversized BLOCK audit persisted body content before secret/PII inspection")
        if entry.get("content_retention") != "metadata_only":
            failures.append("oversized BLOCK audit was not metadata-only")
        audit_provenance = entry.get("provenance")
        expected_keys = {
            "source_type",
            "trust_level",
            "timestamp",
            "retrieved_at",
            "source_length",
            "repository_length",
            "path_length",
            "commit_sha_length",
            "license_length",
            "url_length",
            "author_length",
            "extra_count",
        }
        if not isinstance(audit_provenance, dict) or set(audit_provenance) != expected_keys:
            failures.append("oversized BLOCK audit retained raw or unexpected provenance fields")

        serialized = json.dumps(entry, ensure_ascii=False)
        forbidden = (
            synthetic_secret,
            synthetic_pii,
            provenance.path,
            provenance.commit_sha,
            provenance.license,
            provenance.url,
            provenance.author,
            raw_body,
        )
        if any(value in serialized for value in forbidden):
            failures.append("oversized BLOCK provenance/body leaked into quarantine JSONL")
        if any(
            str(key) in serialized or str(value) in serialized
            for key, value in provenance.extra.items()
        ):
            failures.append("oversized BLOCK extra provenance leaked into quarantine JSONL")

    return EvalOutcome(
        case_name="security_oversized_block_provenance_privacy",
        passed=not failures,
        detail="oversized BLOCK audit must be context-free before secret/PII inspection",
        failures=tuple(failures),
    )


def _allowlisted_quarantine_attribution() -> EvalOutcome:
    failures: list[str] = []
    metadata_secret = "ghp_" + ("M" * 24)
    metadata_pii = "metadata.person@example.com"
    body_secret = "ghp_" + ("S" * 24)
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

    with TemporaryDirectory() as data_dir:
        store = QuarantineStore(f"{data_dir}/quarantine.jsonl")
        gate = SecurityGate(
            allowed_repositories=("safe/repo",),
            quarantine_store=store,
        )
        result, screened = gate.screen_document(
            Document(content=f"token={body_secret}", provenance=provenance)
        )
        entries = store.entries()

    if result.decision is not Decision.QUARANTINE:
        failures.append(f"expected QUARANTINE, got {result.decision.value}")
    if screened is not None:
        failures.append("quarantined document became indexable")
    if len(entries) != 1:
        failures.append(f"expected one quarantine audit record, got {len(entries)}")
    else:
        entry = entries[0]
        expected_provenance = {
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
        if entry.get("provenance") != expected_provenance:
            failures.append("allowlisted quarantine retained more than repository-level attribution")

        serialized = json.dumps(entry, ensure_ascii=False)
        forbidden = (
            metadata_secret,
            metadata_pii,
            body_secret,
            provenance.path,
            provenance.commit_sha,
            provenance.license,
            provenance.url,
            provenance.author,
        )
        if any(value in serialized for value in forbidden):
            failures.append("allowlisted quarantine leaked uninspected provenance or body secret")
        if any(
            str(key) in serialized or str(value) in serialized
            for key, value in provenance.extra.items()
        ):
            failures.append("allowlisted quarantine leaked provenance extra data")
        safe_content = entry.get("content")
        if not isinstance(safe_content, str) or "[REDACTED:" not in safe_content:
            failures.append("allowlisted quarantine did not retain a sanitized review copy")

    return EvalOutcome(
        case_name="security_allowlisted_quarantine_attribution",
        passed=not failures,
        detail=(
            "allowlisted quarantine keeps repository attribution while dropping "
            "uninspected provenance values"
        ),
        failures=tuple(failures),
    )


def run_quarantine_provenance_privacy_suite() -> list[EvalOutcome]:
    """Run persistent quarantine provenance/privacy regressions entirely offline."""

    return [
        _rejected_provenance_privacy(),
        _oversized_block_provenance_privacy(),
        _allowlisted_quarantine_attribution(),
    ]
