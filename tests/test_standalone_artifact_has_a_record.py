"""C-1830: an artifact made on its own leaves a record too.

records.py says it exists so 「この game.html はいつ・何から作られたか」 has an
answer a week later; append_record was called from one place, the whole
production. Three ordinary games for 猫, 犬 and 忍者 were three files named
after the template they share.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.records import STANDALONE_LOG_NAME, read_records
from sidra_ai.evals.standalone_artifact_has_a_record import (
    evaluate_standalone_artifact_has_a_record,
)
from sidra_ai.ingestion.state import StateStore


@pytest.fixture()
def service(tmp_path) -> SidraService:
    return SidraService(
        Settings(data_dir=str(tmp_path), model_backend="echo"),
        state_store=StateStore(tmp_path / "state.json"),
    )


def test_standalone_record_eval_passes():
    result = evaluate_standalone_artifact_has_a_record()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


def test_three_games_are_told_apart_by_the_record(service, tmp_path):
    for request in ("猫のゲームを作って", "犬のゲームを作って", "忍者のゲームを作って"):
        service.chat(request)

    records = read_records(tmp_path, log_name=STANDALONE_LOG_NAME)

    assert len(records) == 3
    assert {r.parameters["題"] for r in records} == {"猫", "犬", "忍者"}
    # and each names the file it made, which is the point of the line
    assert all(r.made and r.made[0].endswith(".html") for r in records)


def test_a_message_that_makes_nothing_writes_no_record(service, tmp_path):
    service.chat("こんにちは")
    assert read_records(tmp_path, log_name=STANDALONE_LOG_NAME) == []


def test_a_route_that_builds_nothing_writes_no_record(tmp_path):
    """The greeting above never reaches the router, so it proves nothing here.

    Neither does an empty router: that path returns before the recorder runs.
    These two stubs are the shapes that reach it - a generator that declined,
    and one that made no file (the deck discarded by its own validator).
    """

    from sidra_ai.creation.intent import CreationIntent, CreationKind
    from sidra_ai.creation.router import CreationOutcome, CreationRouter

    def declined(message, intent, facts=None):
        return CreationOutcome(kind=intent.kind, handled=False, summary="なし")

    def made_no_file(message, intent, facts=None):
        return CreationOutcome(kind=intent.kind, handled=True, summary="破棄しました")

    intent = CreationIntent(is_creation=True, kind=CreationKind.GAME)
    for generator in (declined, made_no_file):
        router = CreationRouter(record_dir=tmp_path)
        router.register(CreationKind.GAME, generator)
        router.route("猫のゲームを作って", intent)

    assert not (tmp_path / STANDALONE_LOG_NAME).exists()


def test_the_log_is_not_listed_as_an_artifact(service, tmp_path):
    service.chat("海のアートを作って")
    assert (tmp_path / STANDALONE_LOG_NAME).is_file()
    listed = {p.name for p in (tmp_path / "artifacts").iterdir()}
    assert STANDALONE_LOG_NAME not in listed


def test_the_record_carries_no_retrieved_text(service, tmp_path):
    from sidra_ai.creation.evidence import Fact
    from sidra_ai.creation.intent import detect_creation_intent

    secret = "四半期の解約率は 12.5% だった"
    request = "収益化のスライドを作って"
    service.creation_router.route(
        request,
        detect_creation_intent(request),
        [Fact(text=secret, source="owner/alpha:docs/plan.md")],
    )

    log = (tmp_path / STANDALONE_LOG_NAME).read_text(encoding="utf-8")
    assert secret not in log
    assert "owner/alpha:docs/plan.md" in log


def test_a_parameter_value_with_a_space_survives_read_back(tmp_path: Path):
    from datetime import datetime, timezone

    from sidra_ai.creation.records import format_record

    line = format_record(
        made=["game-fishing.html"],
        evidence=[],
        parameters={"題": "cat game", "template": "fishing"},
        now=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )
    (tmp_path / STANDALONE_LOG_NAME).write_text(
        f"## 生成履歴\n\n{line}\n", encoding="utf-8"
    )

    record = read_records(tmp_path, log_name=STANDALONE_LOG_NAME)[0]

    assert record.parameters["題"] == "cat game"
    assert record.parameters["template"] == "fishing"
