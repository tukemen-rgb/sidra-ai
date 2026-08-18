"""Direct settings-based model construction must not bypass local admission."""

from __future__ import annotations

import pytest

from sidra_ai.config.settings import Settings
from sidra_ai.models.base import ModelUnavailableError
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.models.registry import adapter_from_settings


def test_adapter_from_settings_keeps_echo_dependency_free() -> None:
    adapter = adapter_from_settings(
        Settings(model_backend="echo", model_name="sidra-echo")
    )

    assert isinstance(adapter, EchoModelAdapter)
    assert adapter.requires_paid_api is False


def test_adapter_from_settings_rejects_non_echo_without_runtime_admission() -> None:
    settings = Settings(
        model_backend="ollama",
        model_name="local-q4",
        model_endpoint="http://127.0.0.1:11434",
    )

    with pytest.raises(
        ModelUnavailableError,
        match="reviewed-manifest and observed-VRAM admission",
    ):
        adapter_from_settings(settings)
