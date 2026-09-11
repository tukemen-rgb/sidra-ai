"""Does the artifact/project listing report the true total when capped?

C-1680. ``list_artifacts`` / ``list_projects`` capped their return at
``MAX_LISTED`` (200) and the endpoints returned only ``{"artifacts": [...]}`` -
no true total. The entry page assumes the returned list IS the whole list, so a
machine with more than 200 generated files showed "全 200 件" (200 total) when
there were more, and everything past 200 vanished from the listing. The
functions now return the full listing, the endpoints cap the wire payload at
``MAX_LISTED`` and report the true ``total``, and the page uses it.

The checks drive the real functions and endpoints with more than ``MAX_LISTED``
entries, and confirm the page reads ``result.total``.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path


def _service(data_dir: Path):
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import SecurityGate

    gate = SecurityGate()
    store = DocumentStore(gate)
    settings = Settings(data_dir=str(data_dir))
    return SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate), settings


def _client(data_dir: Path):
    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app

    service, settings = _service(data_dir)
    return TestClient(create_app(service=service, settings=settings))


@dataclass(frozen=True)
class ArtifactTotalResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_artifact_listing_reports_true_total() -> ArtifactTotalResult:
    from sidra_ai.api.artifacts import MAX_LISTED, list_artifacts, list_projects
    from sidra_ai.api.ui import ASK_PAGE

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    n = MAX_LISTED + 5
    tmp = Path(tempfile.mkdtemp())

    # --- build n artifacts and n projects ---
    art_dir = tmp / "artifacts"
    art_dir.mkdir(parents=True)
    for i in range(n):
        (art_dir / f"file{i:04d}.md").write_text("x", encoding="utf-8")
    proj_dir = tmp / "artifacts" / "projects"
    proj_dir.mkdir(parents=True)
    for i in range(n):
        d = proj_dir / f"proj{i:04d}"
        d.mkdir()
        (d / "production-log.md").write_text("x", encoding="utf-8")

    # --- (A) the listing functions return the full set, not a silent 200 ---
    add(len(list_artifacts(tmp)) == n,
        f"A: list_artifacts returned {len(list_artifacts(tmp))}, expected {n}")
    add(len(list_projects(tmp)) == n,
        f"B: list_projects returned {len(list_projects(tmp))}, expected {n}")

    # --- (C) the endpoints cap the wire payload but report the true total ---
    client = _client(tmp)
    a = client.get("/v1/artifacts").json()
    add(a.get("total") == n,
        f"C: /v1/artifacts total={a.get('total')!r}, expected {n}")
    add(len(a.get("artifacts", [])) == MAX_LISTED,
        f"C: /v1/artifacts returned {len(a.get('artifacts', []))} rows, expected {MAX_LISTED}")
    p = client.get("/v1/projects").json()
    add(p.get("total") == n,
        f"D: /v1/projects total={p.get('total')!r}, expected {n}")

    # --- (E) both the artifact and project counts read result.total ---
    # One "result.total != null" guard per listing (loadArtifacts, loadProjects).
    guards = ASK_PAGE.count("result.total != null")
    add(guards >= 2, f"E: result.total used in {guards} listing(s), expected both")

    total = 6
    return ArtifactTotalResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["ArtifactTotalResult", "evaluate_artifact_listing_reports_true_total"]
