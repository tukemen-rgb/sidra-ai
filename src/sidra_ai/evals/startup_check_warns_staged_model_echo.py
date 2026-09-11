"""Does ``sidra-api --check`` surface the staged-model/echo caution?

C-1664. ``staged_model_but_running_echo`` warns when a machine has a reviewed
model manifest but is starting on the ``echo`` backend - the silent failure the
owner lost time to on 2026-09-02 (a new terminal loses ``SIDRA_MODEL_BACKEND``
and the process quietly falls back to echo). That warning was printed only by
the startup banner, and ``--check`` returns before the banner, so the one
command an operator runs to *validate their startup posture* passed without a
word about it. ``--check`` now emits the same caution.

The checks drive ``server.main(["--check"])`` twice: with a manifest staged
(echo + reviewed model = the warned case) the check must still pass but name
the caution; without one (an ordinary echo machine) it must stay quiet. A
control check confirms the warning tracks the real posture.
"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

_MARKERS = ("審査済みモデル", "echo")


def _run_check(*, manifest: bool):
    """Run `sidra-api --check` in a clean env; return (code, stdout, warning)."""
    from sidra_ai.api import server
    from sidra_ai.api.model_admission import MODEL_MANIFEST_FILENAME
    from sidra_ai.config.settings import get_settings, reset_settings_cache

    saved = {k: v for k, v in os.environ.items() if k.startswith("SIDRA_")}
    for k in list(os.environ):
        if k.startswith("SIDRA_"):
            del os.environ[k]
    data_dir = tempfile.mkdtemp()
    os.environ["SIDRA_DATA_DIR"] = data_dir
    if manifest:
        Path(data_dir, MODEL_MANIFEST_FILENAME).write_text("{}", encoding="utf-8")
    try:
        reset_settings_cache()
        settings = get_settings()
        warning = server.staged_model_but_running_echo(settings)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = server.main(["--check"])
        return code, out.getvalue(), warning
    finally:
        for k in list(os.environ):
            if k.startswith("SIDRA_"):
                del os.environ[k]
        os.environ.update(saved)
        reset_settings_cache()


@dataclass(frozen=True)
class CheckWarnResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_startup_check_warns_staged_model_echo() -> CheckWarnResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) staged real model + echo backend: passes, but names the caution ---
    code, out, warning = _run_check(manifest=True)
    add(code == 0, f"A: --check exit {code}, expected 0 (a warning is not a refusal)")
    add(all(m in out for m in _MARKERS),
        f"A: --check did not surface the staged-model/echo caution: {out!r}")
    add(bool(warning),
        "A control: staged_model_but_running_echo should fire for staged+echo")

    # --- (B) ordinary echo machine (no manifest): stays quiet ---
    code, out, warning = _run_check(manifest=False)
    add(code == 0, f"B: --check exit {code}, expected 0")
    add(not any(m in out for m in _MARKERS),
        f"B: --check warned on an ordinary echo start (noise): {out!r}")
    add(not warning,
        "B control: staged_model_but_running_echo should be silent without a manifest")

    total = 6
    return CheckWarnResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["CheckWarnResult", "evaluate_startup_check_warns_staged_model_echo"]
