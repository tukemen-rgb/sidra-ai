from __future__ import annotations

import sys
from types import SimpleNamespace

from sidra_ai.api import server
from sidra_ai.config.settings import Settings


def test_server_refuses_storage_failure_before_bind_without_leaking_details(
    monkeypatch, capsys
) -> None:
    sensitive_path = "/private/operator/sidra/quarantine.jsonl"

    monkeypatch.setattr(server, "get_settings", lambda: Settings())

    class FailingService:
        def __init__(self, *, settings: Settings) -> None:
            raise OSError(f"permission denied: {sensitive_path}")

    monkeypatch.setattr(server, "SidraService", FailingService)

    def unexpected_bind(*args, **kwargs) -> None:
        raise AssertionError("uvicorn.run must not be reached after storage failure")

    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=unexpected_bind))

    assert server.main([]) == 2

    captured = capsys.readouterr()
    assert "local SIDRA storage is unavailable or unsafe" in captured.err
    assert sensitive_path not in captured.err
    assert "permission denied" not in captured.err
    assert captured.out == ""


def test_server_refuses_audit_storage_failure_before_banner_or_bind(
    monkeypatch, capsys
) -> None:
    sensitive_path = "/private/operator/sidra/api_audit.jsonl"
    sentinel_service = object()

    monkeypatch.setattr(server, "get_settings", lambda: Settings())
    monkeypatch.setattr(
        server,
        "SidraService",
        lambda *, settings: sentinel_service,
    )

    def failing_create_app(*, service, settings):
        assert service is sentinel_service
        assert isinstance(settings, Settings)
        raise OSError(f"permission denied: {sensitive_path}")

    monkeypatch.setattr(server, "create_app", failing_create_app)

    def unexpected_bind(*args, **kwargs) -> None:
        raise AssertionError("uvicorn.run must not be reached after audit storage failure")

    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=unexpected_bind))

    assert server.main([]) == 2

    captured = capsys.readouterr()
    assert "local SIDRA storage is unavailable or unsafe" in captured.err
    assert sensitive_path not in captured.err
    assert "permission denied" not in captured.err
    assert captured.out == ""
