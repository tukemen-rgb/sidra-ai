"""A lost audit record must not look like an operation that never happened.

Audit writes are best-effort on purpose: a local disk fault must not turn a
safe model answer into an HTTP error. SECURITY.md gap 2 is the price of that
choice - the failure was swallowed and counted nowhere, so the log read the
same whether nothing occurred or the record was dropped. Of the two readings,
the one an attacker wants is "nothing occurred", and it was free.

These tests pin the counters and, more importantly, where they surface.
`/v1/index` is authenticated; `/health` is not. "The audit log is currently
failing" is exactly what someone who wants unlogged activity would like to
learn without credentials, so it must not appear on the open endpoint - even
though the backlog item permitted either.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.api.audit import ApiAuditEvent, ApiAuditLog
from sidra_ai.api.schemas import HealthResponse
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.ingestion.state import StateStore


@pytest.fixture
def service(settings: Settings, store, gate, client, model, tmp_path) -> SidraService:
    return SidraService(
        settings,
        model=model,
        store=store,
        gate=gate,
        client=client,
        state_store=StateStore(tmp_path / "state.json"),
    )


def _event() -> ApiAuditEvent:
    return ApiAuditEvent(
        operation="chat",
        outcome="allowed",
        decision="allow",
        input_chars=3,
        repository_count=0,
        citation_repositories=(),
        model_invoked=False,
    )


# ------------------------------------------------------------------ counters


def test_a_fresh_log_has_recorded_nothing(tmp_path) -> None:
    durability = ApiAuditLog(tmp_path / "audit.jsonl").durability()

    assert (durability.recorded, durability.failed) == (0, 0)
    assert durability.last_failure_kind == ""


def test_a_successful_write_is_counted(tmp_path) -> None:
    log = ApiAuditLog(tmp_path / "audit.jsonl")

    log.record(_event())
    log.record(_event())

    assert log.durability().recorded == 2
    assert log.durability().failed == 0


def test_a_failed_write_is_counted_and_still_raises(tmp_path) -> None:
    """The count is added; whether to fail the request stays the caller's call."""

    blocked = tmp_path / "audit.jsonl"
    os.mkdir(blocked)
    log = ApiAuditLog(blocked)

    with pytest.raises(OSError):
        log.record(_event())

    durability = log.durability()
    assert (durability.recorded, durability.failed) == (0, 1)
    assert durability.last_failure_kind == "IsADirectoryError"


def test_the_failure_kind_never_carries_the_path(tmp_path) -> None:
    """A class name says what went wrong; a message would say where."""

    blocked = tmp_path / "secret-dir-name.jsonl"
    os.mkdir(blocked)
    log = ApiAuditLog(blocked)

    with pytest.raises(OSError):
        log.record(_event())

    kind = log.durability().last_failure_kind
    assert "secret-dir-name" not in kind
    assert str(tmp_path) not in kind
    assert kind.isidentifier()


# ------------------------------------------------------------------ exposure


def test_index_reports_audit_durability(service: SidraService, settings: Settings) -> None:
    api = TestClient(create_app(service, settings))

    payload = api.get("/v1/index").json()

    assert "audit" in payload
    assert set(payload["audit"]) == {"recorded", "failed", "last_failure_kind"}
    assert payload["audit"]["failed"] == 0


def test_a_dropped_record_becomes_visible(
    service: SidraService, settings: Settings, tmp_path
) -> None:
    """The whole point: the operator can see that the sink stopped keeping up."""

    broken = ApiAuditLog(tmp_path / "broken.jsonl")
    os.mkdir(tmp_path / "broken.jsonl")
    api = TestClient(create_app(service, settings, audit_log=broken))

    first = api.get("/v1/index")

    assert first.status_code == 200, "a disk fault must not fail the request"
    assert first.json()["audit"]["failed"] == 1
    assert first.json()["audit"]["last_failure_kind"] == "IsADirectoryError"


def test_the_count_includes_the_request_being_answered(
    service: SidraService, settings: Settings, tmp_path
) -> None:
    """Read after recording, so the answer does not lag a request behind."""

    broken = ApiAuditLog(tmp_path / "broken.jsonl")
    os.mkdir(tmp_path / "broken.jsonl")
    api = TestClient(create_app(service, settings, audit_log=broken))

    assert api.get("/v1/index").json()["audit"]["failed"] == 1
    assert api.get("/v1/index").json()["audit"]["failed"] == 2


def test_chat_failures_are_counted_too(
    service: SidraService, settings: Settings, tmp_path
) -> None:
    """Every operation reaches the disk through the same method."""

    broken = ApiAuditLog(tmp_path / "broken.jsonl")
    os.mkdir(tmp_path / "broken.jsonl")
    api = TestClient(create_app(service, settings, audit_log=broken))

    assert api.post("/v1/chat", json={"message": "hi"}).status_code == 200
    assert api.get("/v1/index").json()["audit"]["failed"] == 2  # chat, then index


def test_health_stays_silent_about_the_audit_sink() -> None:
    """Unauthenticated callers learn nothing about logging state."""

    assert not [name for name in HealthResponse.model_fields if "audit" in name]


def test_health_response_still_carries_no_durability_data(
    service: SidraService, settings: Settings, tmp_path
) -> None:
    broken = ApiAuditLog(tmp_path / "broken.jsonl")
    os.mkdir(tmp_path / "broken.jsonl")
    api = TestClient(create_app(service, settings, audit_log=broken))

    api.get("/v1/index")  # make the counter non-zero
    body = api.get("/health").text

    assert "audit" not in body
    assert "IsADirectoryError" not in body


def test_index_still_discloses_no_content(
    service: SidraService, settings: Settings
) -> None:
    """The durability field must not become a new export path."""

    api = TestClient(create_app(service, settings))

    payload = api.get("/v1/index").json()["audit"]

    assert all(isinstance(value, (int, str)) for value in payload.values())
    assert payload["last_failure_kind"] == ""
