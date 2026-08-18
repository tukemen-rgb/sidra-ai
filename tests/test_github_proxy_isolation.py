"""Ambient proxy isolation for authenticated read-only GitHub ingestion."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from sidra_ai.ingestion.github_client import HttpxTransport


class _FakeResponse:
    status_code = 200
    headers = {"content-type": "application/json"}
    text = ""

    @staticmethod
    def json() -> dict[str, bool]:
        return {"ok": True}


def test_github_transport_ignores_ambient_proxy_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authenticated GitHub reads must not inherit workstation proxy routing."""

    observed: dict[str, Any] = {}

    class _FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            observed["client_kwargs"] = kwargs

        def __enter__(self) -> _FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def get(self, url: str, **kwargs: Any) -> _FakeResponse:
            observed["url"] = url
            observed["get_kwargs"] = kwargs
            return _FakeResponse()

    monkeypatch.setenv("HTTPS_PROXY", "https://synthetic-proxy.invalid:8443")
    monkeypatch.setenv("ALL_PROXY", "socks5://synthetic-proxy.invalid:1080")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.setattr(httpx, "Client", _FakeClient)

    token = "synthetic-read-only-token"
    response = HttpxTransport()(
        "GET",
        "https://api.github.com/repos/tukemen-rgb/sidra-ai",
        {"Authorization": f"Bearer {token}"},
        7.5,
    )

    assert response.status == 200
    assert response.body == {"ok": True}
    # Assert the property, not the exact kwargs. An equality check on the
    # whole dict fails whenever an unrelated safe option is added, which
    # trains people to loosen the assertion rather than read it.
    assert observed["client_kwargs"]["trust_env"] is False

    # Disabling ambient routing is also what stops SSL_CERT_FILE being read,
    # so a CA has to be named deliberately. Verification itself must never be
    # switched off to compensate.
    assert observed["client_kwargs"].get("verify") is not False
    assert observed["url"] == "https://api.github.com/repos/tukemen-rgb/sidra-ai"
    assert observed["get_kwargs"]["timeout"] == 7.5
    assert observed["get_kwargs"]["headers"]["Authorization"] == f"Bearer {token}"
