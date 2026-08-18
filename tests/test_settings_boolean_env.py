"""Boolean environment settings must fail closed on malformed values."""

from __future__ import annotations

import pytest

from sidra_ai.config.settings import Settings, UnsafeConfigurationError


@pytest.mark.parametrize("value", ["1", "true", "YES", " on "])
def test_prompt_injection_quarantine_accepts_explicit_true_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SIDRA_QUARANTINE_PROMPT_INJECTION", value)

    settings = Settings.from_env()

    assert settings.quarantine_prompt_injection is True


@pytest.mark.parametrize("value", ["0", "false", "NO", " off "])
def test_prompt_injection_quarantine_accepts_explicit_false_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SIDRA_QUARANTINE_PROMPT_INJECTION", value)

    settings = Settings.from_env()

    assert settings.quarantine_prompt_injection is False


@pytest.mark.parametrize("value", ["", "tru", "2", "disabled"])
def test_malformed_prompt_injection_boolean_fails_closed(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SIDRA_QUARANTINE_PROMPT_INJECTION", value)

    with pytest.raises(
        UnsafeConfigurationError,
        match="SIDRA_QUARANTINE_PROMPT_INJECTION must be one of",
    ):
        Settings.from_env()


def test_malformed_public_bind_boolean_is_not_silently_coerced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SIDRA_ALLOW_PUBLIC_BIND", "enable")

    with pytest.raises(
        UnsafeConfigurationError,
        match="SIDRA_ALLOW_PUBLIC_BIND must be one of",
    ):
        Settings.from_env()
