"""Does the published OpenAPI schema declare the auth it actually enforces?

C-1642. Every route but ``/health`` sits behind ``authenticate``, and even
``/openapi.json`` needs the bearer token to fetch. But ``authenticate`` is a
plain function dependency, not a FastAPI security scheme, so the generated
schema advertised no ``securitySchemes`` and no per-operation ``security`` -
it described the whole API as open. A developer who pulled the schema (having
supplied the token to get it) and generated a client got one with no
``Authorization`` header and a 401 on every ``/v1`` call, with nothing in the
contract to explain why.

The checks build the real app, read the schema, and assert the bearer scheme
is declared, that exactly the ``authenticate``-guarded operations carry
``security: [{"bearerAuth": []}]``, that ``/health`` stays open, and that the
schema route itself still refuses an unauthenticated request.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass


def _app():
    from sidra_ai.api.app import create_app
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.echo import EchoModelAdapter

    settings = Settings(data_dir=tempfile.mkdtemp())
    return create_app(SidraService(settings, model=EchoModelAdapter()), settings)


def _authenticated_route_count(app) -> int:
    """How many in-schema operations actually run ``authenticate``."""
    from fastapi.routing import APIRoute

    def flatten(dep):
        yield dep
        for sub in dep.dependencies:
            yield from flatten(sub)

    total = 0
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        names = [d.call.__name__ for d in flatten(route.dependant) if getattr(d, "call", None)]
        if "authenticate" in names:
            total += len(route.methods)
    return total


@dataclass(frozen=True)
class OpenApiBearerResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_openapi_declares_bearer_auth() -> OpenApiBearerResult:
    from fastapi.testclient import TestClient

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    app = _app()
    api = TestClient(app)
    # Loopback with no token: /openapi.json is reachable, and the schema is a
    # static contract that must still declare the auth model.
    resp = api.get("/openapi.json")
    add(resp.status_code == 200, f"/openapi.json not 200 in loopback: {resp.status_code}")
    schema = resp.json() if resp.status_code == 200 else {}

    schemes = schema.get("components", {}).get("securitySchemes", {})
    bearer = schemes.get("bearerAuth", {})
    add("bearerAuth" in schemes, "securitySchemes.bearerAuth missing")
    add(bearer.get("type") == "http", f"bearerAuth.type not http: {bearer.get('type')!r}")
    add(bearer.get("scheme") == "bearer",
        f"bearerAuth.scheme not bearer: {bearer.get('scheme')!r}")

    paths = schema.get("paths", {})
    want = [{"bearerAuth": []}]
    # Every guarded operation must require the bearer token.
    guarded = [
        "/v1/index", "/v1/retrieve", "/v1/chat", "/v1/artifacts",
        "/v1/artifacts/{name}", "/v1/projects", "/v1/projects/{slug}/{name}",
        "/v1/github/analyze",
    ]
    marked = 0
    for p in guarded:
        ops = paths.get(p, {})
        ok = bool(ops) and all(op.get("security") == want for op in ops.values())
        add(ok, f"{p} not marked bearerAuth: {[op.get('security') for op in ops.values()]}")
        if ok:
            marked += 1

    # /health must stay open (no security requirement).
    health_ops = paths.get("/health", {})
    add(bool(health_ops) and all(not op.get("security") for op in health_ops.values()),
        f"/health carries a security requirement: "
        f"{[op.get('security') for op in health_ops.values()]}")

    # The count of marked operations equals the count the routes truly enforce,
    # so the contract cannot drift from enforcement.
    total_security_ops = sum(
        1 for ops in paths.values() for op in ops.values() if op.get("security") == want
    )
    add(total_security_ops == _authenticated_route_count(app),
        f"marked ops {total_security_ops} != authenticated routes "
        f"{_authenticated_route_count(app)}")

    # The schema route itself must still refuse an unauthenticated request when
    # a token is configured (the fix must not touch that boundary).
    prior = os.environ.get("SIDRA_API_TOKEN")
    os.environ["SIDRA_API_TOKEN"] = "openapi-eval-token-0123456789"
    try:
        secured = TestClient(_app())
        add(secured.get("/openapi.json").status_code == 401,
            "/openapi.json reachable without token when a token is set")
    finally:
        if prior is None:
            os.environ.pop("SIDRA_API_TOKEN", None)
        else:
            os.environ["SIDRA_API_TOKEN"] = prior

    # The schema still describes the API (didn't get emptied by the override).
    add("/v1/chat" in paths, "/v1/chat missing from schema")

    total = 4 + len(guarded) + 4
    return OpenApiBearerResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["OpenApiBearerResult", "evaluate_openapi_declares_bearer_auth"]
