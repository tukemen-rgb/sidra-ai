"""Does ``sidra-evals`` parse its arguments like the other CLIs?

C-1672. Three of the four console scripts (``sidra-api``, ``sidra-ask``,
``sidra-quarantine``) build an argparse parser, so ``--help`` prints usage and
an unknown argument is rejected with exit 2. ``sidra-evals`` (``evals.runner``)
was the lone outlier: ``main(argv)`` accepted arguments but never parsed them,
so ``--help`` silently ran the whole suite and returned 0, and a typo'd flag was
swallowed. ``main`` now runs the arguments through a parser first.

The checks drive ``runner.main``: ``--help`` must exit 0 with a usage line
naming the program, an unknown flag must exit 2, and the no-argument run must
still execute the suite and print its JSON report unchanged.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass


def _run(argv):
    """Run runner.main(argv); return (exitcode_or_None, stdout, stderr)."""
    from sidra_ai.evals import runner

    out, err = io.StringIO(), io.StringIO()
    code: object = None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = runner.main(argv)
        except SystemExit as exc:  # argparse --help / usage error
            code = exc.code
    return code, out.getvalue(), err.getvalue()


@dataclass(frozen=True)
class EvalsCliResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_evals_cli_parses_arguments() -> EvalsCliResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) --help prints usage and exits 0 (argparse behaviour) ---
    code, out, err = _run(["--help"])
    help_text = out + err
    add(code == 0, f"A: --help exit {code!r}, expected 0")
    add("usage" in help_text.lower(), f"A: --help printed no usage line: {help_text[:200]!r}")
    add("sidra-evals" in help_text,
        f"A: usage did not name the program: {help_text[:200]!r}")

    # --- (B) an unknown argument is rejected, not swallowed ---
    code, out, err = _run(["--no-such-flag"])
    add(code == 2, f"B: an unknown flag was not rejected: exit {code!r}")

    # --- (C) the no-argument run still executes the suite unchanged ---
    code, out, err = _run([])
    add(code in (0, 1), f"C: no-arg run returned {code!r}, expected 0 or 1")
    add('"total"' in out and '"passed"' in out,
        f"C: the JSON report was not printed: {out[:120]!r}")

    total = 6
    return EvalsCliResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["EvalsCliResult", "evaluate_evals_cli_parses_arguments"]
