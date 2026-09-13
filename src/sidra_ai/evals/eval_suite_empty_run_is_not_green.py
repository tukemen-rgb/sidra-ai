"""Does ``sidra-evals`` refuse to call a run that judged nothing a success?

C-1754. ``sidra-evals`` (``evals/runner.py``) prints ``{total, passed, failed,
failures}`` and exits 0 when every outcome passed. Its verdict, ``EvalReport.ok``,
was ``self.failed == 0`` - and ``failed == 0`` is vacuously true for an empty
report, so a run that produced *no* outcomes reported success and exited 0. A
reader (or CI) trusting exit 0 could not tell "every safety/grounding check
passed" from "no check ran": if a suite silently dropped out of ``run_all`` or an
import degraded to an empty stub, the tool stayed green. This repository already
warns against "a check that reports success without measuring" (the 08-19
failure); the fix applies it to the eval runner's own verdict - ``ok`` now
requires at least one outcome as well as no failures.

The checks drive the real ``EvalReport``/``run_all``/``main`` so the contract is
read from the running code, not restated.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass


def _outcome(passed: bool):
    from sidra_ai.evals.cases import EvalOutcome

    return EvalOutcome(case_name="probe", passed=passed)


@dataclass(frozen=True)
class EmptyRunResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_eval_suite_empty_run_is_not_green() -> EmptyRunResult:
    from sidra_ai.evals.runner import EvalReport, main, run_all

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) a report that ran nothing is not a success -------------------
    add(EvalReport().ok is False,
        "A: an empty EvalReport reports ok (a run that judged nothing is green)")

    # --- (B) a real, non-empty, all-passing report is a success -----------
    add(EvalReport(outcomes=[_outcome(True), _outcome(True)]).ok is True,
        "B: a non-empty all-passing report is not reported ok")

    # --- (C) a single failure sinks the report ----------------------------
    add(EvalReport(outcomes=[_outcome(True), _outcome(False)]).ok is False,
        "C: a report with a failing outcome is still reported ok")

    # --- (D) the real suite actually runs something -----------------------
    #         (guards run_all against silently producing no outcomes)
    add(len(run_all().outcomes) > 0,
        "D: run_all() produced no outcomes")

    # --- (E) the happy path is unchanged: the real suite exits 0 ----------
    #         main() prints its JSON report to stdout; swallow it so this
    #         eval stays quiet when run inside product_metrics --json.
    with contextlib.redirect_stdout(io.StringIO()):
        exit_code = main([])
    add(exit_code == 0,
        "E: main([]) did not exit 0 on the real (passing) suite")

    # --- (F) the bug, encoded directly: no failures is not, by itself,
    #         success. An empty report shows failed==0 and passed==0 yet
    #         must not be ok. ------------------------------------------------
    empty = EvalReport()
    wire = empty.to_dict()
    add(wire["failed"] == 0 and wire["passed"] == 0 and empty.ok is False,
        f"F: 'zero failures' alone reads as success: {wire!r} ok={empty.ok}")

    total = 6
    return EmptyRunResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["EmptyRunResult", "evaluate_eval_suite_empty_run_is_not_green"]
