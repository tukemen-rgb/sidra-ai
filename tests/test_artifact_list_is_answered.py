"""C-1844: asking what was made is answered with the list.

It used to reach the no-evidence abstention that asks for a repository to be
ingested - for a question about files this product had just written.

The same file pins the regression found while writing that: C-1837 widened the
revision kind check to messages with no referent, and 「して」 is a change verb
that sits inside 探して and 確認して, so ordinary corpus questions naming an
artifact kind were answered 「いま修正できるのはゲームだけ」.
"""

from __future__ import annotations

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.artifact_list_is_answered import (
    CORPUS_QUESTIONS,
    evaluate_artifact_list_is_answered,
)
from sidra_ai.ingestion.state import StateStore


@pytest.fixture()
def service(tmp_path) -> SidraService:
    return SidraService(
        Settings(data_dir=str(tmp_path), model_backend="echo"),
        state_store=StateStore(tmp_path / "state.json"),
    )


def test_artifact_list_eval_passes():
    result = evaluate_artifact_list_is_answered()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


def test_with_nothing_made_it_says_so(service):
    result = service.chat("作ったものを一覧で見せて")

    assert result["refusal"] == "artifact_list"
    assert "まだ何も作っていません" in result["answer"]
    assert "ゲーム" in result["answer"]


def test_the_list_names_the_files_and_the_true_total(service, tmp_path):
    """Seven artifacts, a cap of five: it shows some and counts all (C-1680)."""

    from sidra_ai.api.artifacts import list_artifacts

    for request in (
        "猫のゲームを作って",
        "魚のGIFを作って",
        "海のアートを作って",
        "犬のゲームを作って",
        "船の3Dモデルを作って",
        "鳥のGIFを作って",
        "空のアートを作って",
    ):
        service.chat(request)

    answer = service.chat("作ったものを一覧で見せて")["answer"]

    listing = list_artifacts(tmp_path)
    named = sum(1 for artifact in listing if artifact.name in answer)
    assert f"全 {len(listing)} 件" in answer
    assert 0 < named < len(listing), "it must show fewer than it counts"
    assert "十分な根拠がありません" not in answer


@pytest.mark.parametrize("question", CORPUS_QUESTIONS)
def test_a_corpus_question_is_not_a_revision(service, question):
    assert service.chat(question)["refusal"] != "revision_kind"


def test_the_revision_paths_still_work(service):
    service.chat("猫のゲームを作って")

    assert service.chat("さっきのゲームを難しくして")["refused"] is False
    assert service.chat("さっきのGIFを難しくして")["refusal"] == "revision_kind"
    assert service.chat("もっと難しくして")["refusal"] == "revision_target"


def test_a_corpus_query_containing_those_words_is_not_a_listing(service):
    result = service.chat("作ったものの一覧をドキュメントから探して")
    assert result["refusal"] != "artifact_list"
