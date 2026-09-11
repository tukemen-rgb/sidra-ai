"""Does /v1/index surface the background refresher's health?

C-1655. The refresher keeps the index current on its own thread and records a
metadata-only ``RefreshStatus`` every tick - runs, failures,
``consecutive_failures``, ``last_success_at``, ``last_error_type`` and
``repositories_failed`` (the partial-failure signal C-1482 added). That status
is topology-free precisely so it can cross an API boundary, but no endpoint
returned it: an operator running with auto-refresh enabled could not see via
the API that the background ingest was failing every tick. ``/v1/index``
already surfaces the audit sink's health the same way; the refresher's belongs
beside it.

The checks drive the real ``/v1/index`` and assert the ``refresh`` block is
present, complete, equal to the live refresher status, and that a forced
failure tick is reflected on the next request.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

_TOKEN = "refresh-index-eval-token-0123456789"

_EXPECTED_KEYS = {
    "enabled", "running", "interval_seconds", "runs", "failures",
    "consecutive_failures", "last_run_at", "last_success_at",
    "last_error_type", "repositories_changed", "repositories_failed",
}


def _app():
    from sidra_ai.api.app import create_app
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.echo import EchoModelAdapter

    prior = os.environ.get("SIDRA_API_TOKEN")
    os.environ["SIDRA_API_TOKEN"] = _TOKEN
    try:
        settings = Settings(data_dir=tempfile.mkdtemp())
        app = create_app(SidraService(settings, model=EchoModelAdapter()), settings)
    finally:
        if prior is None:
            os.environ.pop("SIDRA_API_TOKEN", None)
        else:
            os.environ["SIDRA_API_TOKEN"] = prior
    return app


def _index(api):
    return api.get("/v1/index", headers={"Authorization": f"Bearer {_TOKEN}"})


@dataclass(frozen=True)
class IndexRefreshResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_index_surfaces_refresh_status() -> IndexRefreshResult:
    from fastapi.testclient import TestClient

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    os.environ["SIDRA_API_TOKEN"] = _TOKEN
    try:
        app = _app()
        api = TestClient(app)

        resp = _index(api)
        add(resp.status_code == 200, f"/v1/index not 200: {resp.status_code}")
        body = resp.json() if resp.status_code == 200 else {}
        refresh = body.get("refresh")
        add(isinstance(refresh, dict), "no 'refresh' block in /v1/index")
        refresh = refresh or {}
        add(set(refresh.keys()) == _EXPECTED_KEYS,
            f"refresh block keys incomplete: {sorted(refresh.keys())}")
        # equals the live refresher status (surfaces the real object)
        live = app.state.refresher.status().to_dict()
        add(refresh == live, f"refresh block != live status: {refresh} vs {live}")
        # default deployment: refresher disabled, not running
        add(refresh.get("enabled") is False and refresh.get("running") is False,
            f"default refresh not disabled/stopped: {refresh.get('enabled')}/{refresh.get('running')}")

        # force a failure tick and confirm the next request reflects it (live, not cached)
        def boom():
            raise RuntimeError("network down /secret/path")

        app.state.refresher.ingest = boom
        app.state.refresher.run_once()
        body2 = _index(api).json()
        r2 = body2.get("refresh", {})
        add(r2.get("consecutive_failures") == 1,
            f"forced failure not reflected: consecutive_failures={r2.get('consecutive_failures')}")
        add(r2.get("failures") == 1, f"failures not reflected: {r2.get('failures')}")
        add(r2.get("last_error_type") == "RuntimeError",
            f"last_error_type not reflected: {r2.get('last_error_type')!r}")
        add("/secret/path" not in str(r2.get("last_error_type", "")),
            "error message leaked into surfaced status")
    finally:
        os.environ.pop("SIDRA_API_TOKEN", None)

    total = 9
    return IndexRefreshResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["IndexRefreshResult", "evaluate_index_surfaces_refresh_status"]
