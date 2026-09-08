"""If the owner turns the semantic pass on, his own `pytest` should check it.

``docs/RUNBOOK_CODER_MODEL_SWAP.md`` part 2 tells him to stage e5-small and set
three environment variables. Everything about that path is covered by tests
that use a stand-in backend - the wiring, the fallback, the fusion - and
nothing had ever driven it with real weights through the API he actually runs.
Those are different things: a stand-in cannot catch a prefix that never
reaches the model, a factory that quietly returns plain BM25, or weights that
load but produce nothing usable.

This skips wherever the weights are absent, which is everywhere by default and
in CI. That is the point rather than a weakness: on the machine where he has
just followed the runbook, this turns his own test run into a check of his own
configuration, using the path *he* configured rather than one written here.

Verified in the development container on 2026-09-08 with multilingual-e5-small:
the retriever is the semantic one, the backend reports itself available, and
the two questions below cite the document that answers them at rank 1.

**What two questions cannot see.** Removing e5's ``query: `` prefix - asking
the model the wrong way round - does not fail this file: both questions still
cite the right document first, because the lexical half carries them. What the
prefix actually moves is rank across the whole judge (MRR 0.349 with the
asymmetric pair, 0.307 with none, 0.321 with one prefix on both sides), and
that is not something two questions can measure. Choosing a question because
it would make this fail would be fitting the test to the break; the 38-question
judge is where a prefix regression shows up, and it is stated here so nobody
reads a pass as more than it is.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

_MODEL_PATH = os.environ.get("SIDRA_EMBEDDING_MODEL_PATH", "").strip()

pytestmark = pytest.mark.skipif(
    not (_MODEL_PATH and Path(_MODEL_PATH).is_dir()),
    reason=(
        "no embedding weights configured; set SIDRA_EMBEDDING_MODEL_PATH to the "
        "directory from RUNBOOK part 2 to have this check your own setup"
    ),
)


@pytest.fixture(scope="module")
def service():
    from measure_outcomes import ingest

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import get_settings, reset_settings_cache
    from sidra_ai.ingestion.state import StateStore
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, SecurityGate

    data_dir = tempfile.mkdtemp()
    previous = {
        name: os.environ.get(name)
        for name in ("SIDRA_MODEL_BACKEND", "SIDRA_DATA_DIR")
    }
    os.environ["SIDRA_MODEL_BACKEND"] = "echo"
    os.environ["SIDRA_DATA_DIR"] = data_dir
    reset_settings_cache()
    try:
        settings = get_settings()
        repository = "tukemen-rgb/sidra-ai"
        gate = SecurityGate(GatePolicy(), allowed_repositories=[repository])
        store = DocumentStore(gate)
        ingest([(repository, ROOT)], store, gate)
        yield SidraService(
            settings,
            store=store,
            gate=gate,
            state_store=StateStore(Path(data_dir) / "state.json"),
        )
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        reset_settings_cache()


def test_the_configured_path_actually_produces_a_semantic_retriever(service) -> None:
    """A factory that fell back to plain BM25 would be silent about it."""

    from sidra_ai.retrieval.embedding import EmbeddingRetriever

    assert isinstance(service.retriever, EmbeddingRetriever), (
        f"weights are configured but the service built a "
        f"{type(service.retriever).__name__}"
    )
    assert service.retriever.semantic_enabled(), (
        f"the backend is not usable: {service.retriever.backend_name}"
    )


@pytest.mark.parametrize(
    "question,expected",
    [
        ("SIDRA のセキュリティ方針は", "docs/SECURITY.md"),
        ("ローカルで動かす手順を教えて", "docs/LOCAL_RUNTIME.md"),
    ],
)
def test_a_japanese_question_reaches_the_document_that_answers_it(
    service, question: str, expected: str
) -> None:
    """Over HTTP, because that is the boundary the owner's browser talks to.

    These two documents are written in English, and until 2026-09-08 neither
    half of retrieval could reach them from a Japanese question at all
    (C-1152). Asking them here means the repair is checked in the
    configuration the runbook recommends, not only in the default one.
    """

    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app

    client = TestClient(create_app(service=service))

    response = client.post("/v1/chat", json={"message": question})

    assert response.status_code == 200, response.text
    body = response.json()
    assert not body["refused"], body.get("refusal") or body.get("reason")
    cited = [citation["path"] for citation in body["citations"]]
    assert cited, "the answer carried no citations at all"
    assert cited[0] == expected, f"{question!r} cited {cited}"
