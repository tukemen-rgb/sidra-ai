"""Redaction helpers.

Redaction replaces a span with a typed placeholder rather than deleting it,
so the shape of the document survives and reviewers can see *that* something
was removed and *what kind* of thing it was.

Only credential classes whose detector shape already implies a large search
space retain a short deterministic fingerprint for cross-file correlation.
PII and low-entropy/unknown secret classes never retain such a fingerprint:
a public deterministic digest can otherwise become an offline guessing oracle.
"""

from __future__ import annotations

import hashlib

PLACEHOLDER_TEMPLATE = "[REDACTED:{label}:{fingerprint}]"
PII_PLACEHOLDER_TEMPLATE = "[REDACTED:{label}]"

# Fingerprints are useful only when the underlying value already has a large
# search space. Keep this as an explicit allowlist so a newly added detector
# label is fingerprint-free by default until its entropy assumptions are
# reviewed. In particular, ``assigned_secret`` may contain values as short as
# six characters and ``basic_auth_url`` accepts four-character passwords.
_FINGERPRINTABLE_SECRET_LABELS = frozenset(
    {
        "github_token",
        "github_fine_grained_token",
        "aws_access_key_id",
        "anthropic_api_key",
        "openai_api_key",
        "slack_token",
        "google_api_key",
        "private_key_block",
        "json_web_token",
        "high_entropy",
    }
)


def fingerprint(value: str) -> str:
    """Short deterministic fingerprint for high-entropy secret correlation.

    This helper is intentionally *not* used for PII or low-entropy secret
    placeholders. The fixed domain separator makes the digest distinct from a
    bare SHA-256 value, but it is public rather than secret and therefore does
    not make guessable values safe against offline enumeration.
    """

    digest = hashlib.sha256(b"sidra-redaction-v1\x00" + value.encode("utf-8"))
    return digest.hexdigest()[:8]


def placeholder(label: str, value: str) -> str:
    """Build a typed redaction placeholder under the correlation policy."""

    if label.startswith("pii_") or label not in _FINGERPRINTABLE_SECRET_LABELS:
        return PII_PLACEHOLDER_TEMPLATE.format(label=label)
    return PLACEHOLDER_TEMPLATE.format(label=label, fingerprint=fingerprint(value))


def _privacy_preserving_label(existing: str, incoming: str) -> str:
    """Prefer a PII label whenever overlapping spans include personal data.

    Secret and PII detectors can legitimately flag the same bytes. For example,
    ``password=alice@example.test`` is both an assigned secret and a personal
    email. Keeping the secret label in that overlap would retain a deterministic
    fingerprint of the email, defeating the invariant that PII never gets a
    public correlation digest. Findings still retain both categories, so the
    placeholder can safely prefer the more privacy-preserving label.
    """

    if incoming.startswith("pii_") and not existing.startswith("pii_"):
        return incoming
    return existing


def redact_spans(content: str, spans: list[tuple[int, int, str]]) -> str:
    """Replace ``(start, end, label)`` spans with placeholders.

    Overlapping spans are merged into one redaction region. The first outermost
    label is kept except when any overlapping finding is PII; in that case a PII
    label wins so the merged placeholder cannot retain a deterministic digest of
    personal information.
    """

    if not spans:
        return content

    ordered = sorted(spans, key=lambda s: (s[0], -(s[1] - s[0])))
    merged: list[tuple[int, int, str]] = []
    for start, end, label in ordered:
        if start < 0 or end > len(content) or start >= end:
            continue
        if merged and start < merged[-1][1]:
            prev_start, prev_end, prev_label = merged[-1]
            merged[-1] = (
                prev_start,
                max(prev_end, end),
                _privacy_preserving_label(prev_label, label),
            )
            continue
        merged.append((start, end, label))

    out: list[str] = []
    cursor = 0
    for start, end, label in merged:
        out.append(content[cursor:start])
        out.append(placeholder(label, content[start:end]))
        cursor = end
    out.append(content[cursor:])
    return "".join(out)


def excerpt(content: str, start: int, end: int, window: int = 24) -> str:
    """Return context-free evidence metadata that is safe to persist.

    Older versions included raw text immediately before and after the detected
    span. When two secrets/PII values were close together, the evidence for one
    finding could therefore persist the *other* sensitive value verbatim in a
    ``GateResult`` or quarantine audit record. Finding metadata already carries
    detector, reason, severity and offsets, so retaining neighboring source text
    is not worth that secondary disclosure risk.

    ``window`` remains in the signature for backwards compatibility with
    callers, but raw surrounding content is deliberately never returned.
    """

    del content, window
    if start < 0 or end <= start:
        return ""
    return f"<<redacted len={end - start}>>"
