"""Storage settings must not collapse into an implicit working directory."""

from __future__ import annotations

import pytest

from sidra_ai.config.settings import Settings, UnsafeConfigurationError


@pytest.mark.parametrize("data_dir", ("", "   ", "\t\r\n"))
def test_settings_reject_blank_data_dir(data_dir: str) -> None:
    settings = Settings(data_dir=data_dir)

    with pytest.raises(UnsafeConfigurationError, match="data_dir must not be empty"):
        settings.validate()


@pytest.mark.parametrize("raw", ("", "   ", "\t"))
def test_from_env_rejects_blank_data_dir(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
) -> None:
    monkeypatch.setenv("SIDRA_DATA_DIR", raw)

    with pytest.raises(UnsafeConfigurationError, match="data_dir must not be empty"):
        Settings.from_env()


def test_from_env_unset_data_dir_keeps_sidra_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SIDRA_DATA_DIR", raising=False)

    assert Settings.from_env().data_dir == ".sidra"


def test_normal_relative_and_spaced_data_dirs_remain_valid() -> None:
    Settings(data_dir=".sidra-local").validate()
    Settings(data_dir="local sidra data").validate()
