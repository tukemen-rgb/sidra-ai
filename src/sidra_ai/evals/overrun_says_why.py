"""Can a run that goes over its time say what it spent it on?

C-1859. Three loops read ``product_metrics.py``'s own runtime line as "this
tree is seconds from a red test", including the one that filed this item.
It was not: the line said 「N of the 300s a run is allowed」 while the only
thing enforcing anything is ``timeout=900`` in
``tests/test_product_metrics.py``, raised there by C-1613 with the note "a
hang-guard, not a performance contract". Measured before any of this was
written: a deliberate ``sleep(60)`` took a run to **327s**, 27s past "the
budget", and ``test_script_runs_and_prints_a_table`` **passed**.

So there were two defects behind one symptom, and this measures both:

* the report named a wall that does not exist, and named no enforced limit
  at all, so 「余裕 +23.2s」 was read as 23 seconds of life left;
* and the case the numbers exist for - a run that is actually killed - could
  not reach them, because the report is assembled after the last section
  returns. A killed run printed nothing about where the time went.

Every rule here is measured by breaking it and checking the count falls: a
rule that cannot fail is not a rule, and rule C in particular is run as a
real child process that is really killed, because "it would print the trail"
is exactly the kind of claim this item exists to stop anyone making.
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OverrunResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load(script: Path):
    """Import ``product_metrics.py`` by path, as the report's own tests do."""

    import importlib.util

    spec = importlib.util.spec_from_file_location("_pm_overrun", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_pm_overrun"] = module
    spec.loader.exec_module(module)
    return module


#: A stand-in run: one section that finishes and one that never will. Kept
#: off the real COLLECTORS so this costs a second rather than four minutes,
#: and so the section it dies in is known rather than guessed.
_CHILD = """
import importlib.util, sys, time
spec = importlib.util.spec_from_file_location("_pm_child", {script!r})
pm = importlib.util.module_from_spec(spec)
sys.modules["_pm_child"] = pm
spec.loader.exec_module(pm)

def _quick(c):
    time.sleep(0.05)

def _never(c):
    time.sleep(120)

pm.COLLECTORS = (("quickly", _quick), ("forever", _never))
pm.collect()
"""


def _killed_run_trail(script: Path) -> tuple[str, str | None]:
    """Run a collector that hangs, kill it, and return what it had said."""

    source = _CHILD.format(script=str(script))
    try:
        done = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(source)],
            capture_output=True,
            text=True,
            # Sized against the thing it waits for, not guessed: importing
            # the script in a child costs 0.15s measured, and the section
            # that finishes sleeps 0.05s. Three seconds is twenty times
            # that, and it is paid on every collector run - a 20s kill
            # would have put 20s onto a run whose whole complaint is its
            # length.
            timeout=3,
            cwd=str(_root()),
        )
    except subprocess.TimeoutExpired as expired:
        stderr = expired.stderr or b""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        return stderr, None
    # Not being killed is itself a failure of the probe, not a pass: the
    # whole rule is about what survives a kill.
    return done.stderr, "the hanging run finished on its own, so nothing was killed"


def evaluate_overrun_says_why(script: Path | None = None) -> OverrunResult:
    script = script or (_root() / "scripts" / "product_metrics.py")
    failures: list[str] = []
    passed = 0

    pm = _load(script)

    # A. The enforced limit is read off the test that carries it, not
    #    restated. Restating is how the old one came to be wrong.
    enforced = pm.enforced_timeout_seconds()
    # Against the tree the script under evaluation actually reads, not this
    # repository: the two coincide in a normal run and diverge under a
    # staged copy, and the version that used this repository scored a copy
    # honestly following a 600s test as wrong because the real test says
    # 900. A judge that only works when pointed at itself is not a judge.
    test_file = pm.ROOT / pm._ENFORCED_IN
    written = [float(n) for n in re.findall(r"timeout=(\d+)", test_file.read_text("utf-8"))]
    if enforced is None:
        failures.append("the enforced limit could not be read at all")
    elif not written:
        failures.append(f"{pm._ENFORCED_IN} names no timeout to read")
    elif enforced != max(written):
        failures.append(
            f"the enforced limit says {enforced:.0f}s, the test says {max(written):.0f}s"
        )
    else:
        passed += 1

    # B. The runtime line names both numbers and says which one bites. The
    #    old line named one number and called it what a run "is allowed".
    collector = pm.Collector()
    collector.timings.extend([("creation", 200.0), ("answers", 20.0)])
    report = pm._runtime_report(collector, 280.0)
    head = report.splitlines()[0] if report else ""
    if enforced is not None and f"{enforced:.0f}s" not in head:
        failures.append(f"the runtime line does not name the enforced limit: {head!r}")
    elif f"{pm.SUBPROCESS_BUDGET_SECONDS:.0f}s" not in head:
        failures.append(f"the runtime line does not name the advisory line: {head!r}")
    elif "advisory" not in head.lower():
        failures.append(
            f"the runtime line does not say which of the two is advisory: {head!r}"
        )
    else:
        passed += 1

    # C. ...and the case all of it exists for: a run that is killed has
    #    already said which sections finished. Really run, really killed.
    trail, problem = _killed_run_trail(script)
    if problem:
        failures.append(problem)
    elif "quickly" not in trail:
        failures.append(
            "a killed run said nothing about the section that did finish "
            f"({trail.strip()[-120:]!r})"
        )
    elif "forever" in trail:
        failures.append(
            "a killed run claimed a time for the section it died inside, "
            "which is the one thing it cannot know"
        )
    else:
        passed += 1

    return OverrunResult(
        passed=not failures,
        checks_passed=passed,
        checks_total=3,
        failures=tuple(failures),
    )
