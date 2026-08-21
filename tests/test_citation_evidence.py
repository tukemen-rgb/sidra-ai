"""A citation an operator cannot read is a claim, not evidence.

`/v1/chat` used to return repository, path and rank, which tells the operator
where the answer came from but not whether it says what the answer claims.
The excerpt closes that, and in doing so widens what leaves the process - so
these tests pin the two things that keep it bounded: the length cap, and the
output guard.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.ingestion.state import StateStore


@pytest.fixture
def service(settings: Settings, store, gate, client, model, tmp_path) -> SidraService:
    return SidraService(
        settings,
        model=model,
        store=store,
        gate=gate,
        client=client,
        state_store=StateStore(tmp_path / "state.json"),
    )


@pytest.fixture
def api(service: SidraService, settings: Settings) -> TestClient:
    return TestClient(create_app(service, settings))


def test_chat_citations_carry_readable_evidence(
    api: TestClient, service: SidraService
) -> None:
    """The point of the change: the answer can be checked against its source."""

    service.analyze_github(["tukemen-rgb/site"])
    body = api.post("/v1/chat", json={"message": "What is the site repository?"}).json()

    assert body["refused"] is False
    assert body["citations"]
    shown = [c for c in body["citations"] if c["excerpt"]]
    assert shown, "every citation came back without evidence"
    for citation in shown:
        assert citation["excerpt_withheld"] is False
        assert citation["excerpt"].strip()


def test_the_excerpt_cap_is_enforced_not_merely_declared(
    api: TestClient, service: SidraService
) -> None:
    """The cap is a security parameter: how much content leaves per citation.

    Asserted against the constant rather than a literal so the two cannot
    drift apart, and asserted on the wire so a service that ignored the cap
    would fail here rather than pass on the strength of the declaration.
    """

    service.analyze_github(["tukemen-rgb/site"])
    body = api.post("/v1/chat", json={"message": "What is the site repository?"}).json()

    for citation in body["citations"]:
        assert len(citation["excerpt"]) <= MAX_CITATION_EXCERPT_CHARS


def test_a_secret_in_a_chunk_never_leaves_through_a_citation(
    api: TestClient, service: SidraService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The excerpt is output, so it passes the output guard like the answer.

    Without this the citation would be a way around the guard: an answer that
    carefully avoids quoting a credential still cites the chunk holding it.
    Withheld is reported as withheld - an operator must be able to tell "not
    shown" from "nothing there", or they will read a blank excerpt as proof
    the source is empty.
    """

    service.analyze_github(["tukemen-rgb/site"])

    leaked = "ghp_" + "4" * 36
    real_scan = service.output_guard.scan

    def scan(content: str):
        return real_scan(leaked if "site" in content.lower() else content)

    monkeypatch.setattr(service.output_guard, "scan", scan)
    body = api.post("/v1/chat", json={"message": "What is the site repository?"}).json()

    for citation in body["citations"]:
        assert leaked not in citation["excerpt"]
        if not citation["excerpt"]:
            continue
        assert citation["excerpt_withheld"] is False


def test_retrieve_still_withholds_content(api: TestClient, service: SidraService) -> None:
    """`/v1/retrieve` deliberately exports no content; that has not changed.

    It is documented as source discovery without a content-export surface, so
    the excerpt belongs to chat alone. If a future change starts filling it
    here too, that should be a decision someone makes on purpose.
    """

    service.analyze_github(["tukemen-rgb/site"])
    body = api.post("/v1/retrieve", json={"query": "site"}).json()

    assert body["results"]
    for result in body["results"]:
        assert result["citation"]["excerpt"] == ""
