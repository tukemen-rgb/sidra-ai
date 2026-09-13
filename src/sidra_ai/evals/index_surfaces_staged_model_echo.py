"""Does the authenticated runtime status endpoint reveal a silent echo fallback?

C-1761. ``echo`` is the clean-machine default and a legitimate backend, so
``/health`` (unauthenticated, and deliberately model-name-free) says only
``model_available: true``. But when a *reviewed* model is staged here and the
process still runs echo - the lost-``SIDRA_MODEL_BACKEND`` fallback the owner lost
time to on 2026-09-02 - the startup banner and the offline preflight warn, while
the authenticated runtime status endpoint ``/v1/index`` stayed silent. So echo
output looked like a real model's to anyone checking status after boot.

``/v1/index`` now carries ``staged_model_but_running_echo`` beside the audit and
refresh operational facts (C-1655's pattern); ``/health`` must not (its boundary
excludes model names). The checks drive the real service and the real endpoints.
"""

from __future__ import annotations

import dataclasses
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _service_with(*, staged: bool, backend: str = "echo"):
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.manifest import MODEL_MANIFEST_FILENAME

    tmp = tempfile.mkdtemp()
    if staged:
        (Path(tmp) / MODEL_MANIFEST_FILENAME).write_text("{}", encoding="utf-8")
    settings = Settings(data_dir=tmp)
    service = SidraService(settings)
    # Build with echo (Settings is frozen and a real backend would need an
    # endpoint), then swap the whole settings object on the service to exercise
    # the non-echo branch of the advisory without standing up a real model.
    if backend != "echo":
        service.settings = dataclasses.replace(service.settings, model_backend=backend)
    return service, service.settings


@dataclass(frozen=True)
class StagedEchoResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_index_surfaces_staged_model_echo() -> StagedEchoResult:
    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app
    from sidra_ai.api.schemas import IndexResponse

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    FIELD = "staged_model_but_running_echo"

    # --- (A) echo + a staged manifest => flagged --------------------------
    svc, _ = _service_with(staged=True)
    add(svc.index_stats().get(FIELD) is True,
        f"A: index_stats does not flag staged model running echo: {svc.index_stats().get(FIELD)!r}")

    # --- (B) echo + no manifest => not flagged (clean default is quiet) ----
    svc_clean, _ = _service_with(staged=False)
    add(svc_clean.index_stats().get(FIELD) is False,
        f"B: a clean echo default was falsely flagged: {svc_clean.index_stats().get(FIELD)!r}")

    # --- (C) the real /v1/index carries it end to end ---------------------
    svc_c, settings_c = _service_with(staged=True)
    client = TestClient(create_app(service=svc_c, settings=settings_c))
    body = client.get("/v1/index").json()
    add(body.get(FIELD) is True,
        f"C: /v1/index did not surface {FIELD}: {body.get(FIELD)!r}")

    # --- (D) /health must NOT carry it or any model name (boundary) -------
    health = client.get("/health").json()
    add(FIELD not in health and "model_backend" not in health and "backend" not in health,
        f"D: /health leaked the model backend/advisory: {sorted(health)}")

    # --- (E) a non-echo backend is not flagged (echo-specific) -----------
    svc_real, _ = _service_with(staged=True, backend="ollama")
    add(svc_real.index_stats().get(FIELD) is False,
        f"E: a non-echo backend was flagged: {svc_real.index_stats().get(FIELD)!r}")

    # --- (F) the schema default is False (no noise for the common case) ---
    add(getattr(IndexResponse(), FIELD, "MISSING") is False,
        "F: IndexResponse has no staged_model_but_running_echo field (default False)")

    total = 6
    return StagedEchoResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["StagedEchoResult", "evaluate_index_surfaces_staged_model_echo"]
