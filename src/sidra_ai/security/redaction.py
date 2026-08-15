"""Redaction helpers.

Redaction replaces a span with a typed placeholder rather than deleting it,
so the shape of the document survives and reviewers can see *that* something
was removed and *what kind* of thing it was.
"""

from __future__ import annotations

import hashlib

PLACEHOLDER_TEMPLATE = "[REDACTED:{label}:{fingerprint}]"


def fingerprint(value: str) -> str:
    """Short, non-reversible fingerprint of a redacted value.

    Lets an operator confirm "the same key appears in three files" without
    ever storing the key. Salted with a fixed domain string so the digest is
    not directly comparable to a bare SHA-256 of the secret.
    """

    digest = hashlib.sha256(b"sidra-redaction-v1\x00" + value.encode("utf-8"))
    return digest.hexdigest()[:8]


def placeholder(label: str, value: str) -> str:
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
    """Redacted context around a finding, safe to store in an audit log."""

    if start < 0 or end <= start:
        return ""
    left = content[max(0, start - window) : start]
    right = content[end : min(len(content), end + window)]
    return f"{left}<<redacted len={end - start}>>{right}".replace("\n", " ")
