from __future__ import annotations

import sys
from types import SimpleNamespace

from sidra_ai.api import server
from sidra_ai.config.settings import Settings


def test_server_disables_uvicorn_proxy_header_client_rewriting(monkeypatch) -> None:
    settings = Settings()
    sentinel_service = object()
    sentinel_app = object()
    captured: dict[str, object] = {}

    monkeypatch.setattr(server, "get_settings", lambda: settings)
    monkeypatch.setattr(server, "SidraService", lambda *, settings: sentinel_service)
    monkeypatch.setattr(
        server,
        "create_app",
        lambda *, service, settings: sentinel_app,
    )

    def run(app, **kwargs) -> None:
        captured["app"] = app
        captured.update(kwargs)

    # Uvicorn normally allows trusted proxy ranges to come from this process
    # environment. SIDRA's launcher must not let that change request.client,
    # because the private API rate limiter keys its buckets by that address.
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=run))

    assert server.main([]) == 0
    assert captured["app"] is sentinel_app
    assert captured["host"] == settings.host
    assert captured["port"] == settings.port
    assert captured["proxy_headers"] is False
