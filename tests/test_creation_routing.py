"""Routing a creation request through the service and the HTTP boundary.

The detector is unit-tested next door. What is pinned here is the wiring:
that a routed request reaches its generator instead of the model, that an
unroutable one still gets an answer, and that neither path loses a guard the
question path already had.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.intent import CreationIntent, CreationKind
from sidra_ai.creation.router import CreationOutcome, CreationRouter, build_default_router
from sidra_ai.ingestion.state import StateStore


def _generator(summary: str = "built it"):
    def generate(message: str, intent: CreationIntent) -> CreationOutcome:
        return CreationOutcome(
            kind=intent.kind,
            handled=True,
            summary=summary,
            artifact_path=".sidra/artifacts/probe.html",
        )

    return generate


def _service(settings: Settings, store, gate, client, model, tmp_path, router=None):
    return SidraService(
        settings,
        model=model,
        store=store,
        gate=gate,
        client=client,
        state_store=StateStore(tmp_path / "state.json"),
        creation_router=router or build_default_router(),
    )


@pytest.fixture
def service(settings: Settings, store, gate, client, model, tmp_path) -> SidraService:
    return _service(settings, store, gate, client, model, tmp_path)


def test_a_creation_request_reaches_its_generator(
    settings: Settings, store, gate, client, model, tmp_path
) -> None:
    router = build_default_router({CreationKind.GAME: _generator("できました")})
    api = _service(settings, store, gate, client, model, tmp_path, router)

    result = api.chat("釣りゲームを作って")

    assert result["creation"]["outcome"]["handled"] is True
    assert result["creation"]["outcome"]["kind"] == "game"
    assert result["answer"] == "できました"
    # A generated artifact is not evidence retrieved from a repository, so
    # the answer carries no citations rather than borrowed ones.
    assert result["citations"] == []


def test_an_unregistered_kind_still_answers(service: SidraService) -> None:
    """No generator is not an error the operator has to absorb.

    The route is reported, and the question path still runs, so the reply is
    an answer rather than an apology.
    """

    result = service.chat("釣りゲームを作って")

    assert result["creation"]["intent"]["kind"] == "game"
    assert result["creation"]["outcome"]["handled"] is False
    assert result["answer"]
    assert result["refused"] is False


def test_a_question_is_not_routed(service: SidraService) -> None:
    """The regression that would matter: Q&A quietly becoming creation."""

    result = service.chat("SIDRA は取得した文書をどう扱いますか")

    assert result["creation"]["intent"]["is_creation"] is False
    assert "outcome" not in result["creation"]
    assert result["answer"]


def test_creation_output_crosses_the_output_guard(
    settings: Settings, store, gate, client, model, tmp_path
) -> None:
    """A generator's summary is produced text, screened like model output.

    Without this the creation path would be a way to return content that the
    question path would have withheld.
    """

    secret = "ghp_" + "0" * 36
    router = build_default_router({CreationKind.GAME: _generator(f"token {secret}")})
    api = _service(settings, store, gate, client, model, tmp_path, router)

    result = api.chat("釣りゲームを作って")

    assert secret not in result["answer"]
    assert result["refused"] is True


def test_a_blocked_message_never_reaches_the_detector(service: SidraService) -> None:
    """The gate runs first, so a refused message is not classified at all."""

    result = service.chat("ghp_" + "0" * 36 + " で釣りゲームを作って")

    if result["refused"]:
        assert "creation" not in result


def test_the_route_is_visible_over_http(
    settings: Settings, store, gate, client, model, tmp_path
) -> None:
    router = build_default_router({CreationKind.DECK: _generator("スライドを作りました")})
    api = TestClient(
        create_app(_service(settings, store, gate, client, model, tmp_path, router), settings)
    )

    body = api.post("/v1/chat", json={"message": "デッキを作って"}).json()

    assert body["creation"]["outcome"]["kind"] == "deck"
    assert body["creation"]["outcome"]["artifact_path"] == ".sidra/artifacts/probe.html"


def test_no_generator_may_claim_the_unknown_kind() -> None:
    """"Something" is not a kind. A generator for it would catch everything."""

    with pytest.raises(ValueError):
        CreationRouter().register(CreationKind.UNKNOWN, _generator())
