from __future__ import annotations

import math

import pytest

from sidra_ai.config.settings import Settings, UnsafeConfigurationError


@pytest.mark.parametrize(
    "value",
    [0.0, -1.0, math.inf, -math.inf, math.nan, True],
)
def test_settings_reject_invalid_github_request_timeout(value: float) -> None:
    with pytest.raises(
        UnsafeConfigurationError,
        match="github_request_timeout must be a finite positive number",
    ):
        Settings(github_request_timeout=value)


def test_settings_accept_small_finite_positive_github_request_timeout() -> None:
    settings = Settings(github_request_timeout=0.001)

    settings.validate()
    assert settings.github_request_timeout == 0.001


def test_default_github_request_timeout_stays_bounded() -> None:
    settings = Settings()

    assert math.isfinite(settings.github_request_timeout)
    assert settings.github_request_timeout > 0
