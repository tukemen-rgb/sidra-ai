"""The FastAPI factory must enforce the same private-settings boundary as CLI startup."""

from __future__ import annotations

import pytest

from sidra_ai.api.app import create_app
from sidra_ai.config.settings import Settings, UnsafeConfigurationError


def test_create_app_refuses_direct_unreviewed_public_bind(tmp_path) -> None:
    """Direct Settings injection must not bypass ``Settings.validate()``."""

    data_dir = tmp_path / "sidra-data"
    settings = Settings(host="0.0.0.0", data_dir=str(data_dir))

    with pytest.raises(UnsafeConfigurationError, match="non-loopback"):
        create_app(settings=settings)

    # Validation happens before even the local audit sink is constructed.
    assert not data_dir.exists()


def test_create_app_keeps_explicit_authenticated_public_opt_in(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hardening must not remove the existing reviewed explicit opt-in."""

    monkeypatch.setenv("SIDRA_API_TOKEN", "synthetic-local-test-token")
    settings = Settings(
        host="0.0.0.0",
        allow_public_bind=True,
        data_dir=str(tmp_path / "sidra-data"),
    )

    app = create_app(settings=settings)
    assert app.title == "SIDRA AI"
