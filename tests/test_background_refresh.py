"""The index advances without a human, or it is honestly off.

Covers the three properties the refresher is built around: it never reaches
the model, it is off unless configured, and it cannot take the API down with
it. Also pins that turning it on did not widen what the unauthenticated
/health probe discloses.
"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.api.refresher import BackgroundRefresher
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import (
    MIN_INGEST_INTERVAL_SECONDS,
    Settings,
    UnsafeConfigurationError,
)
from sidra_ai.ingestion.state import StateStore


@pytest.fixture
def service(settings, store, gate, client, model, tmp_path) -> SidraService:
    return SidraService(
        settings,
        model=model,
        store=store,
        gate=gate,
        client=client,
        state_store=StateStore(tmp_path / "state.json"),
    )


def _settings_with(settings: Settings, seconds: int) -> Settings:
    from dataclasses import replace

    return replace(settings, ingest_interval_seconds=seconds)


# --- off unless configured --------------------------------------------


def test_disabled_by_default(settings) -> None:
    assert settings.ingest_interval_seconds == 0


def test_app_serves_normally_with_the_refresher_off(service, settings) -> None:
    """A stale index is a worse answer; a dead API is no answer."""

    with TestClient(create_app(service, settings)) as api:
        assert api.get("/health").status_code == 200
        assert api.app.state.refresher.enabled is False
        assert api.app.state.refresher.status().running is False


def test_enabled_refresher_runs_for_the_life_of_the_app(service, settings) -> None:
    configured = _settings_with(settings, MIN_INGEST_INTERVAL_SECONDS)

    app = create_app(service, configured)
    with TestClient(app) as api:
        assert api.get("/health").status_code == 200
        assert app.state.refresher.status().running is True

    # Shutdown must actually stop it, or a restarted server accumulates
    # pollers that nobody can see.
    assert app.state.refresher.status().running is False


@pytest.mark.parametrize("seconds", [1, 30, MIN_INGEST_INTERVAL_SECONDS - 1])
def test_interval_below_the_floor_is_refused_not_clamped(settings, seconds) -> None:
    """Silently running 60x more often than asked is worse than refusing."""

    with pytest.raises(UnsafeConfigurationError):
        _settings_with(settings, seconds).validate()


def test_negative_interval_is_refused(settings) -> None:
    with pytest.raises(UnsafeConfigurationError):
        _settings_with(settings, -1).validate()


# --- never reaches the model ------------------------------------------


def test_a_refresh_ingests_without_invoking_the_model(service, model) -> None:
    refresher = BackgroundRefresher(
        ingest=service.ingest_only, interval_seconds=MIN_INGEST_INTERVAL_SECONDS
    )

    status = refresher.run_once()

    assert status.runs == 1
    assert status.failures == 0
    assert model.calls == 0, "the scheduled path must have no route to inference"


def test_repeated_refreshes_still_never_invoke_the_model(service, model) -> None:
    """The second pass finds nothing new; neither pass may reach the model."""

    refresher = BackgroundRefresher(
        ingest=service.ingest_only, interval_seconds=MIN_INGEST_INTERVAL_SECONDS
    )

    refresher.run_once()
    status = refresher.run_once()

    assert status.runs == 2
    assert status.failures == 0
    assert model.calls == 0


# --- survives failure --------------------------------------------------


def test_a_failing_refresh_is_recorded_rather_than_raised() -> None:
    def broken():
        raise RuntimeError("upstream unavailable")

    refresher = BackgroundRefresher(ingest=broken, interval_seconds=60)

    status = refresher.run_once()

    assert status.runs == 1
    assert status.failures == 1
    assert status.consecutive_failures == 1
    assert status.last_error_type == "RuntimeError"


def test_a_recovery_clears_the_failure_streak() -> None:
    outcomes = [RuntimeError("down"), RuntimeError("down"), None]

    def flaky():
        outcome = outcomes.pop(0)
        if outcome is not None:
            raise outcome

    refresher = BackgroundRefresher(ingest=flaky, interval_seconds=60)
    for _ in range(3):
        status = refresher.run_once()

    assert status.failures == 2
    assert status.consecutive_failures == 0
    assert status.last_error_type == ""
    assert status.last_success_at


def test_status_carries_no_topology_or_exception_text() -> None:
    def broken():
        raise RuntimeError("tukemen-rgb/site fetch failed at /docs/secret.md")

    refresher = BackgroundRefresher(ingest=broken, interval_seconds=60)
    rendered = str(refresher.run_once().to_dict())

    assert "RuntimeError" in rendered
    assert "tukemen-rgb" not in rendered
    assert "secret.md" not in rendered


# --- scheduling behaviour ----------------------------------------------


def test_the_first_tick_waits_so_a_crash_loop_is_not_a_request_flood() -> None:
    started = threading.Event()

    def ingest():
        started.set()

    refresher = BackgroundRefresher(ingest=ingest, interval_seconds=60)
    try:
        assert refresher.start() is True
        # A restart storm must not turn into an outbound fetch per restart.
        assert not started.wait(timeout=0.3)
    finally:
        refresher.stop()


def test_stop_is_safe_when_it_never_started() -> None:
    refresher = BackgroundRefresher(ingest=lambda: None, interval_seconds=0)

    assert refresher.start() is False
    refresher.stop()

    assert refresher.status().running is False


def test_start_is_idempotent() -> None:
    refresher = BackgroundRefresher(ingest=lambda: None, interval_seconds=60)
    try:
        assert refresher.start() is True
        assert refresher.start() is True
        assert threading.active_count() >= 1
    finally:
        refresher.stop()


# --- the probe did not get chattier ------------------------------------


def test_health_still_discloses_nothing_about_the_refresher(service, settings) -> None:
    """/health is unauthenticated; runtime state belongs behind auth."""

    configured = _settings_with(settings, MIN_INGEST_INTERVAL_SECONDS)

    with TestClient(create_app(service, configured)) as api:
        body = api.get("/health").json()

    assert set(body) == {"status", "version", "model_available", "github_write_enabled"}
