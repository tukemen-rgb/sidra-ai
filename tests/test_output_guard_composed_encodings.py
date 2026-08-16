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


def test_output_guard_fails_closed_when_base64_candidate_budget_is_exhausted() -> None:
    """A secret after 32 valid decodes must not be silently skipped."""

    safe = base64.b64encode(b"SIDRA AI local model").decode("ascii")
    secret = _synthetic_github_token()
    encoded_secret = base64.b64encode(secret.encode("utf-8")).decode("ascii")
    text = " ".join([safe] * 32 + [encoded_secret])

    result = OutputGuard().scan(text)

    assert result.blocked
    assert result.reason == "output security detector failed closed"
    assert encoded_secret not in result.content
    assert secret not in repr(result)


def test_output_guard_fails_closed_when_global_variant_budget_is_exhausted() -> None:
    """A 65th unique decoded variant must fail closed instead of being ignored."""

    secret = _synthetic_github_token()

    class SaturatingGuard(OutputGuard):
        @staticmethod
        def _decoded_detection_variants(content: str) -> tuple[str, ...]:
            if content == "safe root":
                return tuple(f"safe base64 variant {i}" for i in range(32))
            return ()

        @staticmethod
        def _percent_decoded_detection_variants(content: str) -> tuple[str, ...]:
            if content == "safe root":
                return tuple(f"safe percent variant {i}" for i in range(32))
            return ()

        @staticmethod
        def _hex_decoded_detection_variants(content: str) -> tuple[str, ...]:
            if content == "safe root":
                return (secret,)
            return ()

        @staticmethod
        def _escaped_detection_variants(content: str) -> tuple[str, ...]:
            return ()

    result = SaturatingGuard().scan("safe root")

    assert result.blocked
    assert result.reason == "output security detector failed closed"
    assert secret not in repr(result)
