from __future__ import annotations

import json

from sidra_ai.security.decisions import Decision
from sidra_ai.security.detectors import SourceAllowlistDetector
from sidra_ai.security.gate import QuarantineStore, SecurityGate


def _untrusted_identifiers() -> tuple[str, str, str, str]:
    synthetic_secret = "ghp_" + "A" * 24
    synthetic_pii = "private.person@example.com"
    source = f"{synthetic_secret}:{synthetic_pii}"
    repository = f"{synthetic_secret}/{synthetic_pii}"
    return source, repository, synthetic_secret, synthetic_pii


def test_unpermitted_source_findings_do_not_echo_raw_identifiers() -> None:
    source, repository, synthetic_secret, synthetic_pii = _untrusted_identifiers()
    detector = SourceAllowlistDetector(allowed_repositories=("safe/repo",))

    output = detector.check(source=source, repository=repository)

    assert len(output.findings) == 2
    by_detector = {finding.detector: finding for finding in output.findings}
    assert by_detector["source"].reason == "source is not on the allowlist"
    assert by_detector["source"].metadata == {"source_length": len(source)}
    assert by_detector["repository"].reason == "repository is not on the allowlist"
    assert by_detector["repository"].metadata == {
        "repository_length": len(repository)
    }

    serialized = json.dumps(
        [finding.to_dict() for finding in output.findings],
        ensure_ascii=False,
    )
    assert synthetic_secret not in serialized
    assert synthetic_pii not in serialized
    assert source not in serialized
    assert repository not in serialized


def test_blocked_source_quarantine_does_not_persist_rejected_identifier_values(
    tmp_path,
) -> None:
    source, repository, synthetic_secret, synthetic_pii = _untrusted_identifiers()
    store = QuarantineStore(tmp_path / "quarantine.jsonl")
    gate = SecurityGate(
        allowed_repositories=("safe/repo",),
        quarantine_store=store,
    )

    result = gate.inspect(
        "body is not inspected after source rejection",
        source=source,
        repository=repository,
    )

    assert result.decision is Decision.BLOCK
    entries = store.entries()
    assert len(entries) == 1
    assert entries[0]["content"] is None
    assert entries[0]["content_retention"] == "metadata_only"

    serialized = json.dumps(
        {"gate": result.to_dict(), "quarantine": entries},
        ensure_ascii=False,
    )
    assert synthetic_secret not in serialized
    assert synthetic_pii not in serialized
    assert source not in serialized
    assert repository not in serialized
