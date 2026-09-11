"""Does a usage-ledger disk failure stay out of the user's answer?

C-1686. ``UsageLedger.record`` appends the record in memory and then writes it to
disk. The write could raise (a full disk, an unwritable path, a permission
error), and with no guard it propagated through ``generate`` and turned a good
local answer into an HTTP 500. Usage accounting is best-effort - the API audit
log already catches this ("a local disk failure must not turn a safe model
response into an HTTP error"), and the ledger now does too.

The checks make the ledger path unwritable (a directory where the file belongs)
and confirm ``record`` and a metered ``generate`` do not raise, the record is
still counted in memory, and a writable path still persists to disk.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UsageBestEffortResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_usage_ledger_disk_write_is_best_effort() -> UsageBestEffortResult:
    from sidra_ai.models.base import GenerationRequest
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.models.usage import MeteredAdapter, UsageLedger

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    def _kwargs():
        return dict(backend="ollama", model="m", input_tokens=1,
                    output_tokens=1, duration_seconds=0.1)

    # --- (A) record() does not raise when the disk write fails ---
    bad = Path(tempfile.mkdtemp()) / "usage.jsonl"
    bad.mkdir()  # a directory where the file belongs: open("a") would raise
    ledger = UsageLedger(bad)
    raised = None
    try:
        ledger.record(**_kwargs())
    except Exception as exc:  # noqa: BLE001 - the bug is an uncaught raise
        raised = f"{type(exc).__name__}: {exc}"
    add(raised is None, f"A: record() raised on an unwritable path: {raised}")

    # --- (B) the record is still counted in memory ---
    add(len(ledger) == 1 and ledger.totals().get("calls") == 1,
        f"B: the record was not kept in memory (len={len(ledger)})")

    # --- (C) a metered generate() over an unwritable ledger does not raise ---
    bad2 = Path(tempfile.mkdtemp()) / "usage.jsonl"
    bad2.mkdir()
    metered = MeteredAdapter(EchoModelAdapter(), UsageLedger(bad2))
    gen_raised = None
    try:
        result = metered.generate(
            GenerationRequest(system_prompt="s", user_message="hello", max_output_tokens=16)
        )
        ok = bool(result.text)
    except Exception as exc:  # noqa: BLE001
        gen_raised = f"{type(exc).__name__}: {exc}"
        ok = False
    add(gen_raised is None and ok, f"C: metered generate() failed on disk error: {gen_raised}")

    # --- (D) a writable path still persists to disk (best-effort didn't break it) ---
    good = Path(tempfile.mkdtemp()) / "usage.jsonl"
    wledger = UsageLedger(good)
    wledger.record(**_kwargs())
    persisted = good.is_file() and len(good.read_text(encoding="utf-8").splitlines()) == 1
    add(persisted, f"D: a writable ledger did not persist to disk (exists={good.exists()})")

    total = 6
    # A and C are the two behaviours that flip; B and D are the invariants that a
    # too-broad "swallow everything" would break. Count each once, plus a repeat
    # of the two flips under a second writable-then-unwritable pair for stability.
    # (kept simple: 4 asserts above map to 4 checks; two more below.)

    # --- (E) totals() still reflects the writable record ---
    add(wledger.totals().get("calls") == 1, "E: writable record not counted in totals")

    # --- (F) an unwritable ledger keeps accumulating in memory across calls ---
    try:
        ledger.record(**_kwargs())
        add(len(ledger) == 2, f"F: unwritable ledger stopped accumulating (len={len(ledger)})")
    except Exception as exc:  # noqa: BLE001 - broken code raises here too
        add(False, f"F: a second record() on an unwritable ledger raised: {type(exc).__name__}")

    return UsageBestEffortResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["UsageBestEffortResult", "evaluate_usage_ledger_disk_write_is_best_effort"]
