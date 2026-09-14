"""Security/behaviour eval suite. Runs offline, with no model weights.

Writing a new eval: ``checks_total`` should be **derived, not written down**.

    return SomeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),   # not `total = 7`
        failures=tuple(failures),
    )

A literal denominator is correct the day it is typed and silently wrong
afterwards. Add a check and forget the number and the metric reads
``10.0 * passed / total`` against a total that no longer counts every check -
so a run with one failing check can report a **perfect score**, because
``checks_passed`` happens to equal the stale ``total``. That is the family
C-1755, C-1791 and C-1795 are about: a number that cannot fall.

Measured 2026-09-14 across all 157 evals then present: **no denominator had
actually drifted**, so this is a trap rather than a bug - and the ones that
looked like drift were all false alarms (a ``total = 0`` counting itself up,
``add()`` in both arms of a try/except or an if/else, and loops). The rule is
written here rather than enforced by a guard for the reason C-1798 gives one
file over in ``scripts/product_metrics.py``: the population cannot be
recovered mechanically, and a number tuned until it is green is the very
defect this family names.

Placement is the honest caveat. This note was first written only in a loop
log, and an eval added the next day used a literal again - which is the
evidence that a rule kept where the work is not does not reach anyone.
"""

from sidra_ai.evals.cases import GATE_CASES, EvalOutcome, GateCase
from sidra_ai.evals.runner import EvalReport, run_all, run_gate_case

__all__ = [
    "GATE_CASES",
    "EvalOutcome",
    "EvalReport",
    "GateCase",
    "run_all",
    "run_gate_case",
]
