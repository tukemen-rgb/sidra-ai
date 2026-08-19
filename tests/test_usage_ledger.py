"""Measuring inference cost, and proving the external part is zero.

Zero external spend is the point of the project. It was reported as a
hard-coded 0.0, which is an assertion rather than evidence. These tests cover
the measurement that replaces it.
"""

from __future__ import annotations

import json

import pytest

from sidra_ai.models.base import GenerationRequest, GenerationResult, LocalModelAdapter
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.models.usage import (
    MeteredAdapter,
    PaidBackendUsageError,
    UsageLedger,
)


def _request(message: str = "what changed?") -> GenerationRequest:
    return GenerationRequest(system_prompt="s", user_message=message)


# --- the ledger --------------------------------------------------------

def test_an_empty_ledger_reports_zero_of_everything() -> None:
    totals = UsageLedger().totals()
    assert totals["calls"] == 0
    assert totals["total_tokens"] == 0
    assert totals["external_api_cost_usd"] == 0.0


def test_totals_accumulate_across_calls() -> None:
    ledger = UsageLedger()
    for _ in range(3):
        ledger.record(
            backend="echo", model="m", input_tokens=100, output_tokens=20,
            duration_seconds=0.5,
        )
    totals = ledger.totals()
    assert totals["calls"] == 3
    assert totals["input_tokens"] == 300
    assert totals["output_tokens"] == 60
    assert totals["total_tokens"] == 360
    assert totals["calls_by_backend"] == {"echo": 3}


def test_throughput_is_derived_not_asserted() -> None:
    ledger = UsageLedger()
    ledger.record(
        backend="llama_cpp", model="m", input_tokens=10, output_tokens=100,
        duration_seconds=2.0,
    )
    assert ledger.totals()["tokens_per_second"] == 50.0


def test_zero_duration_does_not_divide_by_zero() -> None:
    ledger = UsageLedger()
    ledger.record(
        backend="echo", model="m", input_tokens=1, output_tokens=1,
        duration_seconds=0.0,
    )
    assert ledger.totals()["tokens_per_second"] == 0.0


def test_external_cost_is_summed_from_calls_not_hard_coded() -> None:
    """The number has to be capable of being nonzero, or it proves nothing."""

    ledger = UsageLedger()
    ledger.record(
        backend="echo", model="m", input_tokens=5, output_tokens=5,
        duration_seconds=0.1,
    )
    totals = ledger.totals()
    assert totals["external_api_cost_usd"] == 0.0
    assert totals["paid_calls"] == 0


def test_a_paid_call_is_refused_loudly(caplog) -> None:
    """The ledger is what would notice. It must not shrug."""

    ledger = UsageLedger()
    with pytest.raises(PaidBackendUsageError, match="local backends only"):
        ledger.record(
            backend="some_paid_api", model="m", input_tokens=1, output_tokens=1,
            duration_seconds=0.1, requires_paid_api=True,
        )
    assert len(ledger) == 0


def test_a_nonzero_cost_is_refused_even_from_a_local_backend() -> None:
    ledger = UsageLedger()
    with pytest.raises(PaidBackendUsageError):
        ledger.record(
            backend="ollama", model="m", input_tokens=1, output_tokens=1,
            duration_seconds=0.1, external_cost_usd=0.01,
        )


def test_the_ledger_holds_no_prompt_or_response_text(tmp_path) -> None:
    """An accounting record must not become another place a secret rests."""

    path = tmp_path / "usage.jsonl"
    ledger = UsageLedger(path)
    metered = MeteredAdapter(EchoModelAdapter(), ledger)
    metered.generate(_request("my password is hunter2-correct-horse"))

    written = path.read_text(encoding="utf-8")
    assert "hunter2" not in written
    record = json.loads(written.splitlines()[0])
    assert set(record) == {
        "backend", "model", "input_tokens", "output_tokens",
        "duration_seconds", "external_cost_usd", "at",
    }


def test_persisted_ledger_is_owner_only(tmp_path) -> None:
    path = tmp_path / "usage.jsonl"
    ledger = UsageLedger(path)
    ledger.record(
        backend="echo", model="m", input_tokens=1, output_tokens=1,
        duration_seconds=0.1,
    )
    assert (path.stat().st_mode & 0o777) == 0o600


# --- the wrapper -------------------------------------------------------

def test_metered_adapter_records_every_call() -> None:
    ledger = UsageLedger()
    metered = MeteredAdapter(EchoModelAdapter(), ledger)
    for _ in range(4):
        metered.generate(_request())
    assert ledger.totals()["calls"] == 4


def test_metered_adapter_returns_the_inner_result_unchanged() -> None:
    inner = EchoModelAdapter()
    direct = inner.generate(_request("same question"))
    metered = MeteredAdapter(inner, UsageLedger()).generate(_request("same question"))
    assert metered.text == direct.text
    assert metered.backend == direct.backend


def test_metering_measures_real_elapsed_time() -> None:
    class Slow(LocalModelAdapter):
        backend = "slow"

        def generate(self, request: GenerationRequest) -> GenerationResult:
            import time

            time.sleep(0.05)
            return GenerationResult(text="x", backend="slow", model="m")

    ledger = UsageLedger()
    MeteredAdapter(Slow("m"), ledger).generate(_request())
    assert ledger.totals()["inference_seconds"] >= 0.05


def test_a_paid_backend_cannot_be_metered_silently() -> None:
    class Paid(LocalModelAdapter):
        backend = "paid"
        requires_paid_api = True

        def generate(self, request: GenerationRequest) -> GenerationResult:
            return GenerationResult(text="x", backend="paid", model="m")

    with pytest.raises(PaidBackendUsageError):
        MeteredAdapter(Paid("m"), UsageLedger()).generate(_request())


def test_wrapper_forwards_backend_specific_attributes() -> None:
    """Backends carry extras; the wrapper must not hide them."""

    inner = EchoModelAdapter()
    inner.custom_attribute = "present"  # type: ignore[attr-defined]
    metered = MeteredAdapter(inner, UsageLedger())
    assert metered.custom_attribute == "present"
    assert metered.health()["metered"] is True


# --- through the service ----------------------------------------------

def test_service_reports_measured_rather_than_constant_cost(
    settings, store, gate, client, tmp_path
) -> None:
    from sidra_ai.api.service import SidraService
    from sidra_ai.ingestion.state import StateStore

    service = SidraService(
        settings, model=EchoModelAdapter(), store=store, gate=gate, client=client,
        state_store=StateStore(tmp_path / "state.json"),
    )
    assert service.usage.totals()["calls"] == 0

    answer = service.chat("what is indexed?")
    assert answer["model"]["external_api_cost_usd"] == 0.0
    assert service.usage.totals()["calls"] == 1
    assert service.usage.totals()["total_tokens"] > 0
