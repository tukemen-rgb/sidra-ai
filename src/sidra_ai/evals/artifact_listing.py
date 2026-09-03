"""Does the artifact listing show deliverables, not plumbing?

C-1209: every generation put two rows in the ask page's file list - the
playable ``game-*.html`` and its ``game-*.meta.json`` revision sidecar
(C-1112's parameter record). The sidecar is read by the revise path's own
filesystem glob, never through the listing, and clicked by an operator it
downloads 157 bytes of JSON. Half the list was noise.

Four checks over a real artifacts directory: both deliverables listed, no
sidecar listed, and the sidecar still downloadable by name - hiding it from
the list must not take it away from the revise path or a debugging operator.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactListingResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_artifact_listing() -> ArtifactListingResult:
    from sidra_ai.api.artifacts import list_artifacts, read_artifact

    data_dir = Path(tempfile.mkdtemp(prefix="artifact-listing-"))
    directory = data_dir / "artifacts"
    directory.mkdir()
    (directory / "game-fishing-20260903T000000Z.html").write_text(
        "<!doctype html>", encoding="utf-8"
    )
    (directory / "game-fishing-20260903T000000Z.meta.json").write_text(
        '{"template": "fishing"}', encoding="utf-8"
    )
    (directory / "doc-report-20260903T000000Z.md").write_text("# report", encoding="utf-8")
    # A deliverable with "meta" in its ordinary name: hiding by substring
    # instead of by the exact sidecar suffix must fail this eval.
    (directory / "doc-metadata-plan.md").write_text("# plan", encoding="utf-8")

    names = {artifact.name for artifact in list_artifacts(data_dir)}
    checks = 0
    failures: list[str] = []

    if "game-fishing-20260903T000000Z.html" in names:
        checks += 1
    else:
        failures.append("the playable page fell out of the listing")
    if "doc-report-20260903T000000Z.md" in names and "doc-metadata-plan.md" in names:
        checks += 1
    else:
        failures.append("a document fell out of the listing")
    if not any(name.endswith(".meta.json") for name in names):
        checks += 1
    else:
        failures.append("a revision sidecar is still listed")
    try:
        body, _ = read_artifact(data_dir, "game-fishing-20260903T000000Z.meta.json")
        if body:
            checks += 1
        else:
            failures.append("the sidecar came back empty by name")
    except Exception:  # noqa: BLE001 - the check is that this does not raise
        failures.append("hiding the sidecar also removed it from download")

    return ArtifactListingResult(
        passed=not failures, checks_passed=checks, checks_total=4,
        failures=tuple(failures),
    )
