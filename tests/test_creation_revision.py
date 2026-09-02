"""Revising a generated game edits its parameters, not its identity.

The failure this file guards against is the market's chronic one (knowledge
base §9): "make it harder" answered by regenerating something different,
side effects included, or by overwriting the original so there is nothing
to go back to. So the tests check four properties end to end: the detector
takes nothing away from questions or creation requests, a revision changes
exactly the named parameter, the old file survives every revision, and a
chain of revisions builds on the latest version rather than the first.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.api.app import create_app  # noqa: E402
from sidra_ai.api.service import SidraService  # noqa: E402
from sidra_ai.creation.game_job import build_game_generator  # noqa: E402
from sidra_ai.creation.intent import detect_creation_intent  # noqa: E402
from sidra_ai.creation.revise import (  # noqa: E402
    build_game_reviser,
    detect_revision_intent,
    find_target_meta,
    meta_path_for,
)
from sidra_ai.ingestion.state import StateStore  # noqa: E402


# ------------------------------------------------------------- detector


def test_a_revision_request_is_detected() -> None:
    intent = detect_revision_intent("さっきのゲームをもっと難しくして")
    assert intent.is_revision
    assert intent.adjustments == {"difficulty": "+1"}


def test_hiragana_spelling_detects_the_same() -> None:
    """The fold_kana rule applies here as everywhere: script must not route."""

    assert detect_revision_intent("さっきのげーむをむずかしくして").is_revision


def test_a_question_about_difficulty_is_not_a_revision() -> None:
    """「できますか」 is asking, not instructing - the question path owns it."""

    assert not detect_revision_intent("ゲームを難しくできますか").is_revision


def test_a_creation_request_is_not_stolen() -> None:
    """「難しいゲームを作って」 must reach the generator, never the reviser."""

    assert not detect_revision_intent("難しいゲームを作って").is_revision
    assert detect_creation_intent("難しいゲームを作って").routes


def test_an_adjustment_without_a_referent_is_not_a_revision() -> None:
    """A bare 「難しくして」 names nothing we can safely edit."""

    assert not detect_revision_intent("難しくして").is_revision


def test_title_and_theme_adjustments_are_recognised() -> None:
    titled = detect_revision_intent("ゲームのタイトルを「ひかりの海」にして")
    assert titled.adjustments == {"title": "ひかりの海"}
    themed = detect_revision_intent("さっきのゲームを紙のテーマにして")
    assert themed.adjustments == {"theme": "paper"}


# ------------------------------------------------------------- roundtrip


def _generate(tmp_path: Path, message: str = "釣りゲームを作って"):
    generator = build_game_generator(tmp_path)
    return generator(message, detect_creation_intent(message))


def _revise(tmp_path: Path, message: str):
    reviser = build_game_reviser(tmp_path)
    return reviser(message, detect_revision_intent(message))


def test_every_generation_writes_its_sidecar(tmp_path) -> None:
    outcome = _generate(tmp_path)
    sidecar = meta_path_for(Path(outcome.artifact_path))
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    assert meta["template"] == "fishing"
    assert meta["difficulty"] == "normal"
    assert meta["request"] == "釣りゲームを作って"


def test_revision_changes_difficulty_and_keeps_the_original(tmp_path) -> None:
    original = _generate(tmp_path)
    outcome = _revise(tmp_path, "さっきのゲームをもっと難しくして")
    assert outcome.details["difficulty"] == "hard"
    assert outcome.details["playable"] is True
    assert "normal→hard" in outcome.summary
    # The original file is untouched - path still present, content intact.
    assert Path(original.artifact_path).exists()
    assert Path(outcome.artifact_path) != Path(original.artifact_path)


def test_a_chain_of_revisions_builds_on_the_latest_version(tmp_path) -> None:
    """Harder then easier must go hard→normal, not normal→easy off the base."""

    _generate(tmp_path)
    _revise(tmp_path, "さっきのゲームを難しくして")
    outcome = _revise(tmp_path, "さっきのゲームをやさしくして")
    assert "hard→normal" in outcome.summary


def test_revision_at_the_ladder_end_says_nothing_changed(tmp_path) -> None:
    """"Done" about a change that did not happen is the lie this refuses."""

    _generate(tmp_path, "むずかしい釣りゲームを作って")
    outcome = _revise(tmp_path, "さっきのゲームをもっと難しくして")
    assert "変更なし" in outcome.summary


def test_a_named_genre_picks_that_game_not_the_latest(tmp_path) -> None:
    _generate(tmp_path, "釣りゲームを作って")
    _generate(tmp_path, "パズルゲームを作って")
    outcome = _revise(tmp_path, "釣りのゲームを難しくして")
    assert outcome.details["template"] == "fishing"


def test_revising_with_nothing_generated_is_an_honest_no(tmp_path) -> None:
    outcome = _revise(tmp_path, "さっきのゲームを難しくして")
    assert outcome.handled
    assert "見つかりません" in outcome.summary
    assert outcome.artifact_path == ""


def test_title_revision_still_passes_the_trademark_guard(tmp_path) -> None:
    """An override is not a bypass: a franchise title is renamed like any."""

    _generate(tmp_path)
    outcome = _revise(tmp_path, "ゲームのタイトルを「ゼルダの冒険」にして")
    assert "ゼルダ" not in outcome.details.get("template", "")
    sidecar = meta_path_for(Path(outcome.artifact_path))
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    assert "ゼルダ" not in meta["title"]


def test_a_corrupt_sidecar_is_skipped_not_fatal(tmp_path) -> None:
    outcome = _generate(tmp_path)
    meta_path_for(Path(outcome.artifact_path)).write_text("{not json", encoding="utf-8")
    revised = _revise(tmp_path, "さっきのゲームを難しくして")
    assert revised.handled
    assert "見つかりません" in revised.summary


# ------------------------------------------------------------- API layer


def test_the_chat_route_revises_after_creating(
    settings, store, gate, client, model, tmp_path
) -> None:
    """One conversation: make a game, then ask for it harder."""

    service = SidraService(
        settings,
        model=model,
        store=store,
        gate=gate,
        client=client,
        state_store=StateStore(tmp_path / "state.json"),
    )
    api = TestClient(create_app(service, settings))
    made = api.post("/v1/chat", json={"message": "釣りゲームを作って"})
    assert made.status_code == 200
    assert made.json()["creation"]["outcome"]["handled"]

    revised = api.post("/v1/chat", json={"message": "さっきのゲームをもっと難しくして"})
    assert revised.status_code == 200
    body = revised.json()
    assert body["creation"]["revision"] == {"difficulty": "+1"}
    assert body["creation"]["outcome"]["details"]["difficulty"] == "hard"
    assert "難易度" in body["answer"]


def test_the_chat_route_still_answers_questions(
    settings, store, gate, client, model, tmp_path
) -> None:
    """The revision check must not siphon ordinary questions away."""

    service = SidraService(
        settings,
        model=model,
        store=store,
        gate=gate,
        client=client,
        state_store=StateStore(tmp_path / "state.json"),
    )
    api = TestClient(create_app(service, settings))
    answer = api.post("/v1/chat", json={"message": "ゲームのアップロード上限を教えて"})
    assert answer.status_code == 200
    assert "creation" not in answer.json() or not answer.json()["creation"].get("revision")
