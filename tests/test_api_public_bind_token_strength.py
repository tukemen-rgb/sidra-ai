"""API bearer tokens keep an ASCII-safe auth contract; public bind adds a floor."""

from __future__ import annotations

import pytest

from sidra_ai.config.settings import (
    MIN_PUBLIC_API_TOKEN_CHARS,
    Settings,
    UnsafeConfigurationError,
)


def test_public_bind_rejects_short_api_token(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "short-public-token"
    monkeypatch.setenv("SIDRA_API_TOKEN", token)

    with pytest.raises(UnsafeConfigurationError) as exc_info:
        Settings(host="0.0.0.0", allow_public_bind=True).validate()

    assert f"at least {MIN_PUBLIC_API_TOKEN_CHARS}" in str(exc_info.value)
    assert token not in str(exc_info.value)


def test_public_bind_rejects_non_visible_ascii_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "x" * MIN_PUBLIC_API_TOKEN_CHARS + " "
    monkeypatch.setenv("SIDRA_API_TOKEN", token)

    with pytest.raises(UnsafeConfigurationError, match="visible ASCII"):
        Settings(host="0.0.0.0", allow_public_bind=True).validate()


def test_public_bind_accepts_minimum_visible_ascii_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SIDRA_API_TOKEN", "x" * MIN_PUBLIC_API_TOKEN_CHARS)
    Settings(host="0.0.0.0", allow_public_bind=True).validate()


def test_loopback_does_not_require_public_token_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SIDRA_API_TOKEN", "short")
    Settings(host="127.0.0.1").validate()


@pytest.mark.parametrize(
    "token",
    [
        "local token with spaces",
        "local\ttoken",
        "ローカルトークン",
    ],
)
def test_loopback_rejects_configured_token_outside_visible_ascii(
    monkeypatch: pytest.MonkeyPatch,
    token: str,
) -> None:
    monkeypatch.setenv("SIDRA_API_TOKEN", token)

    with pytest.raises(UnsafeConfigurationError, match="visible ASCII") as exc_info:
        Settings(host="127.0.0.1").validate()

    assert token not in str(exc_info.value)
