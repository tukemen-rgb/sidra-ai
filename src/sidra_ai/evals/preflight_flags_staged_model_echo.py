"""Does ``local_preflight`` surface the staged-model/echo caution?

C-1666. ``local_preflight`` is the diagnostic tool whose own docstring says it
"reports only non-secret aggregate state that is useful before starting
``sidra-api``" - the readiness check a home-PC owner runs first. C-1664 taught
``sidra-api --check`` to name the one silent failure this runtime has (a
reviewed model manifest is staged but the process is starting on ``echo`` -
the 2026-09-02 case where a new terminal loses ``SIDRA_MODEL_BACKEND`` and the
machine quietly answers with echo). The readiness tool itself, however, still
reported ``ok: true`` with no word about it. ``collect_preflight`` now carries a
``staged_model_but_running_echo`` advisory field.

The checks drive ``collect_preflight`` in three real postures: a staged model on
an echo backend (the field must be true, while ``ok`` stays true - a warning is
not a refusal); an ordinary echo machine with no manifest (quiet); and a real
backend with a manifest staged (quiet - the caution is echo-gated).
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

_FIELD = "staged_model_but_running_echo"


def _collect(*, backend: str, manifest: bool) -> dict:
    """Run collect_preflight() in a clean env with the given posture."""
    from sidra_ai.api.model_admission import MODEL_MANIFEST_FILENAME
    from sidra_ai.config.settings import reset_settings_cache
    from sidra_ai.local_preflight import collect_preflight

    saved = {k: v for k, v in os.environ.items() if k.startswith("SIDRA_")}
    for k in list(os.environ):
        if k.startswith("SIDRA_"):
            del os.environ[k]
    data_dir = tempfile.mkdtemp()
    os.environ["SIDRA_DATA_DIR"] = data_dir
    os.environ["SIDRA_MODEL_BACKEND"] = backend
    if manifest:
        Path(data_dir, MODEL_MANIFEST_FILENAME).write_text("{}", encoding="utf-8")
    try:
        reset_settings_cache()
        return collect_preflight()
    finally:
        for k in list(os.environ):
            if k.startswith("SIDRA_"):
                del os.environ[k]
        os.environ.update(saved)
        reset_settings_cache()


@dataclass(frozen=True)
class PreflightEchoResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_preflight_flags_staged_model_echo() -> PreflightEchoResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) staged real model + echo backend: readiness stays green, but the
    #         report names the caution ---
    a = _collect(backend="echo", manifest=True)
    add(a.get("ok") is True,
        f"A: ok={a.get('ok')!r}, expected True (a warning is not a refusal)")
    add(a.get(_FIELD) is True,
        f"A: report did not flag staged-model/echo: {_FIELD}={a.get(_FIELD)!r}")
    add(a.get("configured_backend") == "echo",
        f"A: configured_backend={a.get('configured_backend')!r}, expected echo")

    # --- (B) ordinary echo machine, no manifest: stays quiet ---
    b = _collect(backend="echo", manifest=False)
    add(b.get(_FIELD) is not True,
        f"B: report nagged an ordinary echo start: {_FIELD}={b.get(_FIELD)!r}")
    add(b.get("ok") is True,
        f"B: ok={b.get('ok')!r}, expected True")

    # --- (C) real backend with a manifest staged: the caution is echo-gated ---
    c = _collect(backend="ollama", manifest=True)
    add(c.get(_FIELD) is not True,
        f"C: report flagged a non-echo backend: {_FIELD}={c.get(_FIELD)!r}")

    total = 6
    return PreflightEchoResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["PreflightEchoResult", "evaluate_preflight_flags_staged_model_echo"]
