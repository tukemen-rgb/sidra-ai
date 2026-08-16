"""GitHub API origin pinning for read-only ingestion credentials."""

from __future__ import annotations

import pytest

from sidra_ai.config.settings import Settings, UnsafeConfigurationError


@pytest.mark.parametrize(
    "api_base",
    (
        "http://api.github.com",
        "https://example.com",
        "https://api.github.com.evil.example",
        "https://api.github.com@evil.example",
        "https://user@api.github.com",
        "https://api.github.com:444",
        "https://api.github.com/repos",
        "https://api.github.com?target=elsewhere",
        "https://api.github.com#fragment",
    ),
)
def test_github_api_base_rejects_non_official_origins(api_base: str) -> None:
    with pytest.raises(
        UnsafeConfigurationError,
        match=r"official https://api\.github\.com origin",
    ):
        Settings(github_api_base=api_base)


@pytest.mark.parametrize(
    "api_base",
    (
        "https://api.github.com",
        "https://api.github.com/",
        "https://api.github.com:443",
    ),
)
def test_github_api_base_accepts_only_official_https_origin(api_base: str) -> None:
    settings = Settings(github_api_base=api_base)
    settings.validate()


def test_env_cannot_redirect_read_only_github_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An environment override must fail before a token can reach another host."""

    monkeypatch.setenv("SIDRA_GITHUB_TOKEN", "synthetic-read-only-token")
    monkeypatch.setenv("SIDRA_GITHUB_API_BASE", "https://collector.example")

    with pytest.raises(UnsafeConfigurationError):
        Settings.from_env()
