from __future__ import annotations

import pytest

from sidra_ai.config.settings import Settings, UnsafeConfigurationError


@pytest.mark.parametrize("value", [0, -1])
def test_settings_reject_non_positive_ingestion_item_budget(value: int) -> None:
    settings = Settings(max_items_per_source=value)

    with pytest.raises(
        UnsafeConfigurationError, match="max_items_per_source must be positive"
    ):
        settings.validate()


def test_settings_accept_minimum_positive_ingestion_item_budget() -> None:
    Settings(max_items_per_source=1).validate()


def test_environment_rejects_non_positive_ingestion_item_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SIDRA_MAX_ITEMS_PER_SOURCE", "0")

    with pytest.raises(
        UnsafeConfigurationError, match="max_items_per_source must be positive"
    ):
        Settings.from_env()
