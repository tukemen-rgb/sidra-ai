from __future__ import annotations

import pytest

from sidra_ai.config.settings import Settings, UnsafeConfigurationError


@pytest.mark.parametrize("value", [0, -1])
def test_settings_reject_non_positive_model_output_budget(value: int) -> None:
    settings = Settings(model_max_output_tokens=value)

    with pytest.raises(
        UnsafeConfigurationError, match="model_max_output_tokens must be positive"
    ):
        settings.validate()


def test_settings_accept_minimum_positive_model_output_budget() -> None:
    Settings(model_max_output_tokens=1).validate()


def test_environment_rejects_non_positive_model_output_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SIDRA_MODEL_MAX_OUTPUT_TOKENS", "0")

    with pytest.raises(
        UnsafeConfigurationError, match="model_max_output_tokens must be positive"
    ):
        Settings.from_env()
