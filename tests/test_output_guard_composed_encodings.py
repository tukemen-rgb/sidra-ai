"""Regression tests for composed reversible output encodings."""

from __future__ import annotations

import base64

from sidra_ai.security.output_guard import OutputGuard


def _synthetic_github_token() -> str:
    return "ghp_" + "0" * 36


def test_output_guard_blocks_base64_wrapped_percent_encoded_credential() -> None:
    """base64(percent(secret)) must not bypass a one-layer decoder."""

    secret = _synthetic_github_token()
    percent_encoded = "".join(f"%{byte:02X}" for byte in secret.encode("utf-8"))
    encoded = base64.b64encode(percent_encoded.encode("utf-8")).decode("ascii")

    result = OutputGuard().scan(f"Nested credential: {encoded}")

    assert result.blocked
    assert encoded not in result.content
    assert secret not in repr(result)
    assert "github_token" in result.finding_labels


def test_output_guard_blocks_hex_wrapped_base64_credential() -> None:
    """hex(base64(secret)) must be decoded through both bounded layers."""

    secret = _synthetic_github_token()
    inner = base64.b64encode(secret.encode("utf-8")).decode("ascii")
    encoded = inner.encode("utf-8").hex()

    result = OutputGuard().scan(f"Nested credential: {encoded}")

    assert result.blocked
    assert encoded not in result.content
    assert secret not in repr(result)
    assert "github_token" in result.finding_labels


def test_output_guard_allows_safe_two_layer_encoding_exactly() -> None:
    """Bounded composition scanning must not rewrite safe model output."""

    inner = base64.b64encode(b"SIDRA AI local model").decode("ascii")
    encoded = inner.encode("utf-8").hex()
    text = f"Nested note: {encoded}"

    result = OutputGuard().scan(text)

    assert not result.blocked
    assert result.content == text
