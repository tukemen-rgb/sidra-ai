from __future__ import annotations

import sys

from sidra_ai.api import server
from sidra_ai.config.settings import Settings


def test_startup_check_assembles_without_uvicorn_or_socket(monkeypatch, capsys) -> None:
    settings = Settings()
    sentinel_service = object()
    sentinel_app = object()
    calls = {"service": 0, "app": 0}

    monkeypatch.setattr(server, "get_settings", lambda: settings)

    def build_service(*, settings: Settings):
        calls["service"] += 1
        assert settings.is_localhost_only
        assert settings.model_backend == "echo"
        return sentinel_service

    def build_app(*, service, settings: Settings):
        calls["app"] += 1
        assert service is sentinel_service
        assert settings.is_localhost_only
        return sentinel_app

    monkeypatch.setattr(server, "SidraService", build_service)
    monkeypatch.setattr(server, "create_app", build_app)

    # If the check path attempts to import uvicorn, Python raises ImportError.
    # A successful check therefore proves the serving dependency and socket path
    # are not required after the normal service/app assembly has succeeded.
    monkeypatch.setitem(sys.modules, "uvicorn", None)

    assert server.main(["--check"]) == 0
    assert calls == {"service": 1, "app": 1}

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == "SIDRA AI startup check passed; no socket opened\n"


def test_startup_check_does_not_bypass_non_loopback_validation(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(server, "get_settings", lambda: Settings())

    assert server.main(["--check", "--host", "0.0.0.0"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "refusing to bind non-loopback host" in captured.err
