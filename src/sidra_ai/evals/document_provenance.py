"""Do generated documents carry the provenance of the facts they quote?

C-1203: ``SidraService._facts_for`` read ``repository``/``path`` off the
chunk instead of its provenance, so every fact in every generated document
was labelled 「出典不明」 while the sources section claimed nothing was
retrieved - five excerpts a reader could not verify, produced by the system
whose selling point is source citations.

Measured through the real chat path: a document request whose subject the
corpus genuinely contains must come back as a saved artifact whose facts
name a real repository and path, with no 「出典不明」 anywhere in it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.evals.qa_honesty import _build_service

#: The repository every eval chunk carries, and the path of the ads-policy
#: chunk the probe request below retrieves. Must match qa_honesty's corpus.
_REPOSITORY = "tukemen-rgb/sidra-ai"
_EXPECTED_PATH = "docs/ads.md"


@dataclass(frozen=True)
class DocumentProvenanceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_document_provenance() -> DocumentProvenanceResult:
    service = _build_service()
    checks = 0
    failures: list[str] = []

    result = service.chat("広告の方針のレポートを作って")
    outcome = (result.get("creation") or {}).get("outcome") or {}

    if outcome.get("handled") and outcome.get("kind") == "document":
        checks += 1
    else:
        failures.append("document request was not routed to the document generator")
        return DocumentProvenanceResult(False, checks, 4, tuple(failures))

    markdown = ""
    artifact = Path(outcome.get("artifact_path", ""))
    if artifact.is_file():
        markdown = artifact.read_text(encoding="utf-8")
    if not markdown:
        failures.append("generated artifact file not found")
        return DocumentProvenanceResult(False, checks, 4, tuple(failures))

    if f"{_REPOSITORY} {_EXPECTED_PATH}" in markdown:
        checks += 1
    else:
        failures.append("facts do not name the repository and path they came from")

    if "出典不明" not in markdown:
        checks += 1
    else:
        failures.append("a fact is still labelled 出典不明")

    if f"- {_REPOSITORY} {_EXPECTED_PATH}" in markdown:
        checks += 1
    else:
        failures.append("the sources section does not list the retrieved path")

    return DocumentProvenanceResult(
        passed=not failures, checks_passed=checks, checks_total=4,
        failures=tuple(failures),
    )
