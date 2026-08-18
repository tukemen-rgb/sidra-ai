from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE_DOC = ROOT / "docs" / "ARCHITECTURE.md"


def test_architecture_documents_guarded_schema_surface() -> None:
    architecture = ARCHITECTURE_DOC.read_text(encoding="utf-8")

    assert (
        "four service routes plus one guarded schema endpoint; interactive docs disabled"
        in architecture
    )
    assert "`GET /openapi.json` — authenticated/rate-limited schema discovery" in architecture
    assert "Swagger UI and ReDoc are disabled" in architecture
    assert "| `api/` | private HTTP surface | four routes;" not in architecture
