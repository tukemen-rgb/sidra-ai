"""CLI overrides must be validated even when their values are falsey."""

from __future__ import annotations

import pytest

from sidra_ai.api import server
from sidra_ai.config.settings import Settings


def test_explicit_zero_port_is_rejected_instead_of_falling_back(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(server, "get_settings", lambda: Settings())

    assert server.main(["--port", "0"]) == 2
    assert "port out of range" in capsys.readouterr().err


def test_explicit_empty_host_is_rejected_instead_of_falling_back(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(server, "get_settings", lambda: Settings())

    assert server.main(["--host", ""]) == 2
    assert "non-loopback" in capsys.readouterr().err
