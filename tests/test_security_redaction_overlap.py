"""Regression coverage for overlapping secret/PII redaction spans."""

from __future__ import annotations

from sidra_ai.security.decisions import Decision, FindingCategory
from sidra_ai.security.gate import SecurityGate
from sidra_ai.security.redaction import fingerprint, redact_spans


def test_overlapping_pii_span_disables_secret_fingerprint() -> None:
    """PII must not inherit a secret correlation digest through span merging."""

    personal = "alice@example.test"
    content = f"password={personal}"
    start = content.index(personal)
    end = start + len(personal)

    redacted = redact_spans(
        content,
        [
            (start, end, "assigned_secret"),
            (start, end, "pii_email"),
        ],
    )

    assert redacted == "password=[REDACTED:pii_email]"
    assert personal not in redacted
    assert fingerprint(personal) not in redacted


def test_gate_keeps_secret_pii_overlap_fingerprint_free() -> None:
    """The real gate must preserve both findings without hashing the PII value."""

    personal = "alice@example.test"
    gate = SecurityGate(allowed_repositories=("tukemen-rgb/site",))

    result = gate.inspect(
        f"password={personal}",
        source="github",
        repository="tukemen-rgb/site",
    )

    assert result.decision is Decision.QUARANTINE
    assert result.has(FindingCategory.SECRET)
    assert result.has(FindingCategory.PII)
    assert result.content == "password=[REDACTED:pii_email]"
    assert personal not in result.content
    assert fingerprint(personal) not in result.content
