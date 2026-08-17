"""API rate-limit configuration must fail before an unusable server starts."""

from __future__ import annotations

import pytest

from sidra_ai.api.app import create_app
from sidra_ai.config.settings import Settings, UnsafeConfigurationError


@pytest.mark.parametrize("value", [0, -1])
def test_nonpositive_rate_limit_is_rejected(value: int) -> None:
    settings = Settings(rate_limit_per_minute=value)

    with pytest.raises(UnsafeConfigurationError, match="rate_limit_per_minute must be positive"):
        settings.validate()


def test_app_factory_rejects_nonpositive_rate_limit_before_construction() -> None:
    settings = Settings(rate_limit_per_minute=0)

    with pytest.raises(UnsafeConfigurationError, match="rate_limit_per_minute must be positive"):
        create_app(settings=settings)
