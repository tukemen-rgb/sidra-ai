"""Recall guards for credential-assignment false-positive tuning.

These cases are synthetic and offline. They protect the security boundary from
future detector changes that classify broad value shapes as placeholders.
"""

from __future__ import annotations

import pytest

from sidra_ai.security.decisions import Decision, FindingCategory
from sidra_ai.security.gate import SecurityGate


@pytest.mark.parametrize(
    "text",
    [
        'password = "hunter2)"',
        'api_key = "abc123}"',
        'token = "secret]"',
        'credential = "value77>"',
    ],
)
def test_assigned_secrets_with_closing_delimiters_stay_detected(
    gate: SecurityGate, text: str
) -> None:
    """Closing delimiters may be legitimate secret characters, not placeholders."""

    result = gate.inspect(text, source="github", repository="tukemen-rgb/Fg")

    assert result.has(FindingCategory.SECRET)
    assert result.decision is Decision.QUARANTINE
    assert "assigned_secret" in {finding.detector for finding in result.findings}


@pytest.mark.parametrize(
    "text",
    [
        'password = "string"',
        'password: "current-password"',
        'token = "boolean"',
    ],
)
def test_placeholder_like_words_stay_detected_when_explicitly_assigned(
    gate: SecurityGate, text: str
) -> None:
    """Type/UI words are ambiguous values unless syntax proves they are declarations."""

    result = gate.inspect(text, source="github", repository="tukemen-rgb/Fg")

    assert result.has(FindingCategory.SECRET)
    assert result.decision is Decision.QUARANTINE
    assert "assigned_secret" in {finding.detector for finding in result.findings}
