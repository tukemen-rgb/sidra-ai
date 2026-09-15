"""C-1835: a change asked of a GIF must not edit the latest game.

Revision is game-only. Nothing checked the kind the message named, so
「さっきのGIFを難しくして」 resolved 「さっきの」 to the latest game and wrote a new
version of it - announced as 「「猫」を修正しました」, success under a title the
person had not asked about.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.revise import detect_revision_intent
from sidra_ai.evals.revision_refuses_another_kind import (
    evaluate_revision_refuses_another_kind,
)
from sidra_ai.ingestion.state import StateStore


@pytest.fixture()
def service(tmp_path) -> SidraService:
    svc = SidraService(
        Settings(data_dir=str(tmp_path), model_backend="echo"),
        state_store=StateStore(tmp_path / "state.json"),
    )
    svc.chat("猫のゲームを作って")
    svc.chat("魚のGIFを作って")
    return svc


def _difficulties(root: Path) -> dict[str, str]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))["difficulty"]
        for path in sorted((root / "artifacts").glob("game-*.meta.json"))
    }


def test_revision_kind_eval_passes():
    result = evaluate_revision_refuses_another_kind()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 12


def test_a_gif_request_does_not_edit_the_game(service, tmp_path):
    before = _difficulties(tmp_path)

    result = service.chat("さっきのGIFを難しくして")

    assert _difficulties(tmp_path) == before, "the game was edited anyway"
    assert result["refused"] is True
    assert result["refusal"] == "revision_kind"
    assert "GIF" in result["answer"]


def test_a_slide_request_says_slides_cannot_be_revised(service):
    result = service.chat("さっきのスライドを短くして")

    assert result["refusal"] == "revision_kind"
    assert "スライド" in result["answer"]


def test_a_genuine_game_revision_still_works(service, tmp_path):
    before = _difficulties(tmp_path)

    result = service.chat("さっきのゲームを難しくして")

    assert result["refused"] is False
    assert _difficulties(tmp_path) != before


@pytest.mark.parametrize(
    "message", ["さっきのアートを明るくして", "さっきのレポートを難しくして", "さっきの3Dモデルを大きくして"]
)
def test_every_other_kind_is_refused_too(message):
    assert detect_revision_intent(message).names_other_kind


def test_a_change_naming_no_kind_is_unchanged():
    assert detect_revision_intent("さっきのを難しくして").is_revision
    assert detect_revision_intent("それを簡単にして").is_revision


def test_the_head_noun_decides_which_kind_was_named():
    # 「ゲームの資料」 is a document about a game (C-1479).
    assert detect_revision_intent("さっきのゲームの資料を直して").names_other_kind
    assert detect_revision_intent("さっきの資料のゲームを難しくして").is_revision


def test_the_answer_arrives_in_one_step(service):
    """C-1837: 「GIFを難しくして」 hears 「ゲームだけ」 without a round trip.

    This test asserted the opposite until C-1837. The two-step path - ask for
    「さっきの」, then refuse the kind - is the failure C-1814 named, and the
    cycle that cited C-1814 built it again.
    """

    result = service.chat("GIFを難しくして")

    assert result["refusal"] == "revision_kind"
    assert "ゲームだけ" in result["answer"]


def test_a_change_that_is_neither_pointed_at_nor_readable(service):
    """The fourth corner: it used to ask for a repository to be ingested."""

    result = service.chat("スライドを短くして")

    assert result["refusal"] == "revision_kind"


def test_a_change_naming_no_kind_still_asks_which_one(service):
    """C-1797 keeps its case - there the missing piece really is the target."""

    result = service.chat("もっと難しくして")

    assert result["refusal"] == "revision_target"


def test_naming_a_kind_without_asking_for_a_change_is_not_a_revision(service):
    """What the change-verb gate actually decides, measured.

    「レポートの内容」 names a kind and asks for no change; without the gate it
    is answered 「修正できるのはゲームだけ」. The question and creation cases below
    are held further up, by their own vetoes.
    """

    mention = service.chat("レポートの内容")
    asked = service.chat("スライドの作り方を教えて")
    built = service.chat("スライドを作って")

    assert mention["refusal"] != "revision_kind"
    assert asked["refusal"] != "revision_kind"
    assert built["refusal"] != "revision_kind"
    assert built["creation"]["outcome"]["handled"] is True
