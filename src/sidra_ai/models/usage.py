"""Measuring what inference actually costs.

Reducing external LLM spend to zero is the point of this project, and until
now the API reported ``external_api_cost_usd: 0.0`` as a hard-coded literal.
That is an assertion, not a measurement. A number that cannot change is not
evidence of anything.

Zero external spend is already guaranteed structurally: the registry refuses
to register a backend whose ``requires_paid_api`` is true, so there is no
paid code path to take. This module does not add a guarantee - it makes the
existing one **observable**. A guarantee nobody can see is indistinguishable
from an assumption, and the first time someone asks "how do you know it's
zero?", pointing at a constant is not an answer.

What is recorded is local cost, which is real even when the invoice is not:
tokens processed and wall-clock seconds spent. Those are what tell an
operator whether a 32B model on owned hardware is fast enough to use.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sidra_ai.models.base import (
    GenerationRequest,
    GenerationResult,
    LocalModelAdapter,
)


class PaidBackendUsageError(RuntimeError):
    """Raised if a billed backend ever reaches the ledger.

    The registry should make this unreachable. It is checked anyway because
    the whole purpose of the ledger is to be the thing that notices, and a
    check that only runs when the guarantee already held is worthless.
    """


@dataclass(frozen=True)
class UsageRecord:
    """One inference call."""

    backend: str
    model: str
    input_tokens: int
    output_tokens: int
    duration_seconds: float
    external_cost_usd: float
    at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "duration_seconds": round(self.duration_seconds, 4),
            "external_cost_usd": self.external_cost_usd,
            "at": self.at,
        }


class UsageLedger:
    """Thread-safe accumulator of local inference cost.

    Deliberately holds no prompt or response text. This is an accounting
    record, and a record that carried the content would be one more place a
    secret could come to rest.
    """

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self._lock = threading.RLock()
        self._records: list[UsageRecord] = []
        self._path = Path(path) if path else None

    def record(
        self,
        *,
        backend: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_seconds: float,
        requires_paid_api: bool = False,
        external_cost_usd: float = 0.0,
    ) -> UsageRecord:
        if requires_paid_api or external_cost_usd:
            raise PaidBackendUsageError(
                f"backend {backend!r} reported paid usage "
                f"(${external_cost_usd}). v0.1 runs on local backends only; "
                "this call should have been impossible"
            )

        entry = UsageRecord(
            backend=backend,
            model=model,
            input_tokens=max(0, int(input_tokens)),
            output_tokens=max(0, int(output_tokens)),
            duration_seconds=max(0.0, float(duration_seconds)),
            external_cost_usd=0.0,
            at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._records.append(entry)
            if self._path is not None:
                self._append(entry)
        return entry

    def _append(self, entry: UsageRecord) -> None:
        assert self._path is not None
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.touch(mode=0o600)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._records)

    def totals(self) -> dict[str, Any]:
        """Cumulative usage. ``external_api_cost_usd`` here is counted."""

        with self._lock:
            records = list(self._records)

        by_backend: dict[str, int] = {}
        for record in records:
            by_backend[record.backend] = by_backend.get(record.backend, 0) + 1

        input_tokens = sum(r.input_tokens for r in records)
        output_tokens = sum(r.output_tokens for r in records)
        seconds = sum(r.duration_seconds for r in records)

        return {
            "calls": len(records),
            "calls_by_backend": by_backend,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "inference_seconds": round(seconds, 3),
            "tokens_per_second": (
                round(output_tokens / seconds, 2) if seconds > 0 else 0.0
            ),
            # Summed from what every call reported, not asserted. Any nonzero
            # value would have raised at record time.
            "external_api_cost_usd": sum(r.external_cost_usd for r in records),
            "paid_calls": sum(1 for r in records if r.external_cost_usd),
        }

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


class MeteredAdapter(LocalModelAdapter):
    """Wraps a backend and books every call into a :class:`UsageLedger`.

    A wrapper rather than a change to each adapter, so a future backend is
    metered by construction instead of by remembering to add the call.
    """

    def __init__(self, inner: LocalModelAdapter, ledger: UsageLedger) -> None:
        super().__init__(inner.model, **getattr(inner, "options", {}))
        self.inner = inner
        self.ledger = ledger
        self.backend = inner.backend
        self.requires_paid_api = inner.requires_paid_api

    def generate(self, request: GenerationRequest) -> GenerationResult:
        started = time.monotonic()
        result = self.inner.generate(request)
        elapsed = time.monotonic() - started

        self.ledger.record(
            backend=result.backend or self.inner.backend,
            model=result.model or self.inner.model,
            input_tokens=result.input_tokens_estimate,
            output_tokens=result.output_tokens_estimate,
            duration_seconds=elapsed,
            requires_paid_api=self.inner.requires_paid_api,
            external_cost_usd=float(result.metadata.get("cost_usd", 0.0) or 0.0),
        )
        return result

    def health(self) -> dict[str, Any]:
        info = self.inner.health()
        info["metered"] = True
        return info

    def __getattr__(self, name: str) -> Any:
        # Backends carry their own extras (endpoints, streaming, context
        # limits). Forward rather than shadow them.
        return getattr(self.inner, name)
