"""Do /health and /openapi.json report the same, single-sourced version?

C-1649. ``service.health()`` returns the version from ``sidra_ai.__version__``
(via ``_version()``), but ``create_app`` built the FastAPI app with a hardcoded
``version="0.1.0"`` literal - a second, independent source. They agree only
because both happen to read 0.1.0 today; the next version bump would leave
``/health`` reporting the new version while ``/openapi.json`` still reported the
old one, with no signal which to trust.

The checks build the app at the real package version and under a substituted
``__version__``, and assert both surfaces (and the FastAPI object) track the one
source in step. The substitution is always restored.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass


def _app(token: str | None = None):
    import os

    from sidra_ai.api.app import create_app
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.echo import EchoModelAdapter

    prior = os.environ.get("SIDRA_API_TOKEN")
    if token is None:
        os.environ.pop("SIDRA_API_TOKEN", None)
    else:
        os.environ["SIDRA_API_TOKEN"] = token
    try:
        settings = Settings(data_dir=tempfile.mkdtemp())
        app = create_app(SidraService(settings, model=EchoModelAdapter()), settings)
    finally:
        if prior is None:
            os.environ.pop("SIDRA_API_TOKEN", None)
        else:
            os.environ["SIDRA_API_TOKEN"] = prior
    return app


def _versions(token: str):
    """Return (health_version, openapi_version, app_version) for a fresh app."""
    from fastapi.testclient import TestClient

    app = _app(token=token)
    api = TestClient(app)
    health = api.get("/health").json()["version"]
    openapi = api.get(
        "/openapi.json", headers={"Authorization": f"Bearer {token}"}
    ).json()["info"]["version"]
    return health, openapi, app.version


@dataclass(frozen=True)
class VersionAgreeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_health_openapi_version_agree() -> VersionAgreeResult:
    import sidra_ai

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    token = "version-eval-token-0123456789"

    # --- at the real package version ---
    real = sidra_ai.__version__
    h, o, a = _versions(token)
    add(h == real, f"/health version {h!r} != __version__ {real!r}")
    add(o == real, f"/openapi.json version {o!r} != __version__ {real!r}")
    add(h == o, f"/health {h!r} and /openapi.json {o!r} disagree at real version")
    add(a == real, f"FastAPI app.version {a!r} != __version__ {real!r}")

    # --- under a substituted version, both surfaces must track it ---
    bumped = "9.9.9-eval"
    sidra_ai.__version__ = bumped
    try:
        h2, o2, a2 = _versions(token)
    finally:
        sidra_ai.__version__ = real
    add(h2 == bumped, f"/health did not track bumped version: {h2!r}")
    add(o2 == bumped, f"/openapi.json did not track bumped version: {o2!r}")
    add(h2 == o2, f"/health {h2!r} and /openapi.json {o2!r} disagree after bump")
    add(a2 == bumped, f"FastAPI app.version did not track bump: {a2!r}")

    # --- substitution really was restored ---
    add(sidra_ai.__version__ == real, "package __version__ not restored")

    total = 9
    return VersionAgreeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["VersionAgreeResult", "evaluate_health_openapi_version_agree"]
