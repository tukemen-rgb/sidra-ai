"""Regression tests for HTML-character-reference output exfiltration."""

from __future__ import annotations

import base64

from sidra_ai.security.output_guard import OutputGuard


def _synthetic_github_token() -> str:
    return "ghp_" + "0" * 36


def test_output_guard_blocks_html_entity_encoded_personal_email() -> None:
    personal_email = "kenji.tanaka@example.co.jp"
    encoded = "kenji.tanaka&#64;example.co.jp"

    result = OutputGuard().scan(f"Contact: {encoded}")

    assert result.blocked
    assert result.reason == "secret-like or high-confidence PII detected in model output"
    assert "email" in result.finding_labels
    assert encoded not in result.content
    assert personal_email not in repr(result)


def test_output_guard_blocks_html_entity_encoded_provider_token() -> None:
    secret = _synthetic_github_token()
    encoded = "ghp&#95;" + "0" * 36

    result = OutputGuard().scan(f"Credential: {encoded}")

    assert result.blocked
    assert "github_token" in result.finding_labels
    assert encoded not in result.content
    assert secret not in repr(result)


def test_output_guard_blocks_base64_wrapped_html_entity_credential() -> None:
    """base64(html-entity(secret)) must be caught by the bounded decode graph."""

    secret = _synthetic_github_token()
    entity_encoded = "ghp&#95;" + "0" * 36
    encoded = base64.b64encode(entity_encoded.encode("utf-8")).decode("ascii")

    result = OutputGuard().scan(f"Nested credential: {encoded}")

    assert result.blocked
    assert "github_token" in result.finding_labels
    assert encoded not in result.content
    assert secret not in repr(result)


def test_output_guard_preserves_safe_html_entities_byte_for_byte() -> None:
    text = "AT&amp;T documentation uses &copy; as a rendering example."

    result = OutputGuard().scan(text)

    assert not result.blocked
    assert result.content == text


def test_output_guard_fails_closed_when_html_entity_budget_is_exhausted() -> None:
    text = "&#65;" * 4097

    result = OutputGuard().scan(text)

    assert result.blocked
    assert result.reason == "output security detector failed closed"
    assert text not in result.content
