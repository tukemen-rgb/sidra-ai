"""Regression coverage for secret redaction fingerprint policy."""

from __future__ import annotations

from sidra_ai.security.decisions import Decision, FindingCategory
from sidra_ai.security.gate import SecurityGate
from sidra_ai.security.redaction import fingerprint, placeholder


FAKE_GITHUB_TOKEN = "ghp_" + "7" * 36


def test_assigned_low_entropy_secret_has_no_public_fingerprint() -> None:
    """Guessable password assignments must not create an offline hash oracle."""

    value = "123456"
    gate = SecurityGate(allowed_repositories=("tukemen-rgb/site",))

    result = gate.inspect(
        f"password={value}",
        source="github",
        repository="tukemen-rgb/site",
    )

    assert result.decision is Decision.QUARANTINE
    assert result.has(FindingCategory.SECRET)
    assert result.content == "password=[REDACTED:assigned_secret]"
    assert value not in result.content
    assert fingerprint(value) not in result.content


def test_basic_auth_password_has_no_public_fingerprint() -> None:
    """Short Basic-Auth passwords are also guessable and stay fingerprint-free."""

    value = "12345!"
    gate = SecurityGate(allowed_repositories=("tukemen-rgb/site",))

    result = gate.inspect(
        f"https://user:{value}@example.test/private",
        source="github",
        repository="tukemen-rgb/site",
    )

    assert result.decision is Decision.QUARANTINE
    assert result.has(FindingCategory.SECRET)
    assert not result.has(FindingCategory.PII)
    assert value not in result.content
    assert fingerprint(value) not in result.content
    assert "[REDACTED:basic_auth_url]" in result.content


def test_provider_token_keeps_high_entropy_correlation_fingerprint() -> None:
    """Provider-shaped high-entropy values retain useful cross-file correlation."""

    gate = SecurityGate(allowed_repositories=("tukemen-rgb/site",))
    result = gate.inspect(
        f"config value: {FAKE_GITHUB_TOKEN}",
        source="github",
        repository="tukemen-rgb/site",
    )

    assert result.decision is Decision.QUARANTINE
    assert FAKE_GITHUB_TOKEN not in result.content
    assert fingerprint(FAKE_GITHUB_TOKEN) in result.content


def test_unknown_secret_label_defaults_to_fingerprint_free() -> None:
    """New detector labels must not gain correlation digests without review."""

    value = "guessable"
    rendered = placeholder("future_secret", value)

    assert rendered == "[REDACTED:future_secret]"
    assert fingerprint(value) not in rendered
