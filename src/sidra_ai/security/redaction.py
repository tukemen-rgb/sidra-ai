"""Redaction helpers.

Redaction replaces a span with a typed placeholder rather than deleting it,
so the shape of the document survives and reviewers can see *that* something
was removed and *what kind* of thing it was.

Credential-like secrets may retain a short deterministic fingerprint so an
operator can correlate the same high-entropy value across files. PII never
retains such a fingerprint: many identifiers have a small enough search space
that a public deterministic digest can become a guessing oracle.
"""

from __future__ import annotations

import hashlib

PLACEHOLDER_TEMPLATE = "[REDACTED:{label}:{fingerprint}]"
PII_PLACEHOLDER_TEMPLATE = "[REDACTED:{label}]"


def fingerprint(value: str) -> str:
    """Short deterministic fingerprint for high-entropy secret correlation.

    This helper is intentionally *not* used for PII placeholders. The fixed
    domain separator makes the digest distinct from a bare SHA-256 value, but
    it is public rather than secret and therefore does not make low-entropy
    personal identifiers safe against offline guessing.
    """

    digest = hashlib.sha256(b"sidra-redaction-v1\x00" + value.encode("utf-8"))
    return digest.hexdigest()[:8]


def placeholder(label: str, value: str) -> str:
    """Build a typed redaction placeholder without retaining PII digests."""

    if label.startswith("pii_"):
        return PII_PLACEHOLDER_TEMPLATE.format(label=label)
    return PLACEHOLDER_TEMPLATE.format(label=label, fingerprint=fingerprint(value))


def redact_spans(content: str, spans: list[tuple[int, int, str]]) -> str:
    """Replace ``(start, end, label)`` spans with placeholders.

    Overlapping spans are merged by keeping the first (outermost) label, so a
    value is never partially revealed by a second, narrower redaction.
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
            merged[-1] = (prev_start, max(prev_end, end), prev_label)
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
