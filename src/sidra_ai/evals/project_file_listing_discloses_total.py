"""Does the per-project file listing disclose its true count when truncated?

C-1748. The flat artifacts listing caps the wire payload at ``MAX_LISTED`` but
reports the true total, so the entry page says "全 N 件" instead of the capped
count (C-1680). The per-project file listing never got that fix: ``_project_files``
truncated to ``MAX_LISTED`` *inside the helper* and discarded the count, and
``ProjectListing`` carried no file total. So a production with more than 200 files
(an asset-heavy bundle) was shown with exactly 200 rows and nothing saying files
were hidden - in the one product whose selling point is that a generation is
traceable "from the browser down to" every file.

``_project_files`` now returns the full list; ``ProjectListing.to_dict`` caps the
wire ``files`` at ``MAX_LISTED`` and reports ``file_total``; the web UI shows a
per-project "全 N 件" note the way it already does for the flat listing.

The checks build a project of ``MAX_LISTED + 5`` files: the helper returns them
all, ``to_dict`` caps ``files`` and reports the true ``file_total``, a small
project is unchanged, the real ``/v1/projects`` carries the total, and the web UI
renders the note.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass


def _make_project(n_files: int) -> str:
    from sidra_ai.api.artifacts import projects_dir

    data_dir = tempfile.mkdtemp()
    proj = projects_dir(data_dir) / "shooter"
    proj.mkdir(parents=True)
    for i in range(n_files):
        (proj / f"f{i:04d}.md").write_text("x", encoding="utf-8")
    return data_dir


@dataclass(frozen=True)
class ProjectFileTotalResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_project_file_listing_discloses_total() -> ProjectFileTotalResult:
    from sidra_ai.api.artifacts import MAX_LISTED, _project_files, list_projects, projects_dir

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    big = MAX_LISTED + 5
    big_dir = _make_project(big)
    listing = list_projects(big_dir)[0]
    wire = listing.to_dict()

    # --- (A) to_dict reports the true file total, not the capped count ---
    add(wire.get("file_total") == big,
        f"A: file_total was not the true count: {wire.get('file_total')!r} (want {big})")

    # --- (B) the wire files list is capped at MAX_LISTED ---
    add(len(wire.get("files", [])) == MAX_LISTED,
        f"B: the wire file list was not capped at {MAX_LISTED}: {len(wire.get('files', []))}")

    # --- (C) _project_files returns the full list (total is knowable, not lost) ---
    full = _project_files(projects_dir(big_dir) / "shooter")
    add(len(full) == big,
        f"C: _project_files truncated inside the helper: {len(full)} (want {big})")

    # --- (D) a small project is unchanged (all files, file_total == count) ---
    small_dir = _make_project(3)
    small = list_projects(small_dir)[0].to_dict()
    add(small.get("file_total") == 3 and len(small.get("files", [])) == 3,
        f"D: a small project regressed: file_total={small.get('file_total')!r}, "
        f"files={len(small.get('files', []))}")

    # --- (E) the web UI renders a per-project file total when truncated.
    #         Pin the disclosure guard itself (the note is emitted only when the
    #         true count exceeds the shown rows), not just the substring "全 "
    #         which the project/artifact count notes already carry. ---
    from sidra_ai.api.ui import ASK_PAGE
    import re
    add(re.search(r"p\.file_total", ASK_PAGE) is not None
        and re.search(r"fileTotal > shownFiles", ASK_PAGE) is not None
        and re.search(r"全 \" \+ fileTotal", ASK_PAGE) is not None,
        "E: the web UI does not surface a per-project file_total note")

    # --- (F) the real /v1/projects response carries the total end-to-end ---
    from fastapi.testclient import TestClient
    from sidra_ai.api.app import create_app
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, SecurityGate

    gate = SecurityGate(GatePolicy(), allowed_repositories=())
    settings = Settings(data_dir=big_dir)
    service = SidraService(settings, model=EchoModelAdapter(), store=DocumentStore(gate), gate=gate)
    client = TestClient(create_app(service=service, settings=settings))
    body = client.get("/v1/projects").json()
    proj = (body.get("projects") or [{}])[0]
    add(proj.get("file_total") == big and len(proj.get("files", [])) == MAX_LISTED,
        f"F: /v1/projects did not carry the file total: "
        f"file_total={proj.get('file_total')!r}, files={len(proj.get('files', []))}")

    total = 6
    return ProjectFileTotalResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["ProjectFileTotalResult", "evaluate_project_file_listing_discloses_total"]
