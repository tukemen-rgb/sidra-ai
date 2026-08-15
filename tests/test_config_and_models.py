"""Localhost-by-default, and no paid API anywhere in the dependency graph."""

from __future__ import annotations

import pytest

from sidra_ai.config.settings import (
    DEFAULT_ALLOWED_REPOSITORIES,
    LOCALHOST_ADDRESSES,
    Settings,
    UnsafeConfigurationError,
    reset_settings_cache,
)
from sidra_ai.models.base import LocalModelAdapter, ModelUnavailableError
from sidra_ai.models.registry import (
    PaidBackendRejectedError,
    adapter_from_settings,
    available_backends,
    create_adapter,
    register,
)


# --- binding posture ---------------------------------------------------

def test_default_host_is_loopback() -> None:
    settings = Settings()
    assert settings.host == "127.0.0.1"
    assert settings.host in LOCALHOST_ADDRESSES
    assert settings.is_localhost_only


def test_default_from_env_is_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_settings_cache()
    assert Settings.from_env().is_localhost_only


def test_public_bind_is_refused_without_opt_in() -> None:
    with pytest.raises(UnsafeConfigurationError, match="non-loopback"):
        Settings(host="0.0.0.0").validate()


def test_public_bind_requires_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIDRA_API_TOKEN", raising=False)
    with pytest.raises(UnsafeConfigurationError, match="SIDRA_API_TOKEN"):
        Settings(host="0.0.0.0", allow_public_bind=True).validate()


def test_public_bind_allowed_with_opt_in_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIDRA_API_TOKEN", "a-locally-generated-value")
    Settings(host="0.0.0.0", allow_public_bind=True).validate()


def test_env_var_alone_cannot_expose_the_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting only the host must not be enough to go public."""

    monkeypatch.setenv("SIDRA_HOST", "0.0.0.0")
    reset_settings_cache()
    with pytest.raises(UnsafeConfigurationError):
        Settings.from_env()


def test_server_refuses_to_start_when_unsafe(monkeypatch: pytest.MonkeyPatch) -> None:
    from sidra_ai.api import server

    monkeypatch.setenv("SIDRA_HOST", "0.0.0.0")
    reset_settings_cache()
    assert server.main([]) == 2


# --- secrets never live in settings ------------------------------------

def test_tokens_are_not_stored_in_the_settings_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIDRA_API_TOKEN", "super-secret-value")
    monkeypatch.setenv("SIDRA_GITHUB_TOKEN", "another-secret-value")
    reset_settings_cache()
    settings = Settings.from_env()

    assert "super-secret-value" not in repr(settings)
    assert "another-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings.redacted_dict())
    assert settings.redacted_dict()["api_token_configured"] is True


def test_allowlist_defaults_to_the_five_sidra_repositories() -> None:
    assert set(DEFAULT_ALLOWED_REPOSITORIES) == {
        "tukemen-rgb/site",
        "tukemen-rgb/creater-yard",
        "tukemen-rgb/Fg",
        "tukemen-rgb/marketing",
        "tukemen-rgb/sidra-ai",
    }


def test_repository_allowlist_is_case_insensitive() -> None:
    assert Settings().is_repository_allowed("Tukemen-RGB/Site")
    assert not Settings().is_repository_allowed("tukemen-rgb/other")


# --- model backends ----------------------------------------------------

def test_default_backend_is_local_and_free() -> None:
    settings = Settings()
    assert settings.model_backend == "echo"
    adapter = adapter_from_settings(settings)
    assert adapter.requires_paid_api is False


def test_every_registered_backend_is_free() -> None:
    for name in available_backends():
        adapter_cls = create_adapter(name, "dummy").__class__
        assert adapter_cls.requires_paid_api is False, f"{name} bills per token"


def test_registry_refuses_a_paid_backend() -> None:
    """The constraint is structural: a paid adapter cannot be registered."""

    class PaidAdapter(LocalModelAdapter):
        backend = "some_paid_api"
        requires_paid_api = True

        def generate(self, request):  # pragma: no cover - never runs
            raise NotImplementedError

    with pytest.raises(PaidBackendRejectedError):
        register(PaidAdapter)
    assert "some_paid_api" not in available_backends()


def test_settings_reject_an_unknown_backend() -> None:
    with pytest.raises(UnsafeConfigurationError, match="not a local backend"):
        Settings(model_backend="openai").validate()


def test_remote_model_endpoint_is_refused_by_default() -> None:
    from sidra_ai.models.http_backends import OllamaAdapter

    with pytest.raises(ModelUnavailableError, match="not loopback"):
        OllamaAdapter("llama3", endpoint="http://inference.example.com:11434")


def test_loopback_model_endpoint_is_accepted() -> None:
    from sidra_ai.models.http_backends import LlamaCppAdapter

    adapter = LlamaCppAdapter("local-32b", endpoint="http://127.0.0.1:8080")
    assert adapter.endpoint == "http://127.0.0.1:8080"


def test_echo_backend_works_without_weights_or_network() -> None:
    from sidra_ai.models.base import GenerationRequest
    from sidra_ai.models.echo import EchoModelAdapter

    result = EchoModelAdapter().generate(
        GenerationRequest(system_prompt="s", user_message="what changed?")
    )
    assert result.text
    assert result.metadata["cost_usd"] == 0.0


def test_backends_are_swappable_through_one_interface() -> None:
    for name in available_backends():
        adapter = create_adapter(name, "model-name")
        assert isinstance(adapter, LocalModelAdapter)
        assert hasattr(adapter, "generate")


def test_no_paid_llm_sdk_is_a_dependency() -> None:
    """A paid SDK must never appear in pyproject dependencies."""

    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    required = " ".join(data["project"]["dependencies"]).lower()
    for banned in ("openai", "anthropic", "google-generativeai", "cohere", "mistralai"):
        assert banned not in required, f"{banned} must not be a required dependency"
