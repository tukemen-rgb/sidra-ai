"""C-1269: the English no-evidence reply asks the admin, not the reader.

「No indexed evidence matched this question. Run POST /v1/github/analyze to
ingest the repositories…」 handed a general user a raw internal HTTP call as
their own imperative, while the Japanese reply asked the administrator. The
English framing now routes the ask to the administrator too, keeping the opening
marker and the endpoint token that other judges depend on.
"""

from __future__ import annotations

from sidra_ai.evals.no_evidence_english_admin_framed import (
    evaluate_no_evidence_english_admin_framed,
)
from sidra_ai.models.base import GenerationRequest
from sidra_ai.models.echo import EchoModelAdapter


def _en_no_evidence() -> str:
    return EchoModelAdapter().generate(
        GenerationRequest(
            system_prompt="", user_message="how do I reset my password", data_context=""
        )
    ).text


def test_no_evidence_english_admin_framed_eval_passes():
    result = evaluate_no_evidence_english_admin_framed()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 16


def test_english_reply_asks_administrator_not_the_reader():
    ans = _en_no_evidence()
    assert "administrator" in ans.lower()
    # the reader is no longer told to run the endpoint themselves
    assert "Run POST" not in ans


def test_english_reply_keeps_marker_and_endpoint():
    ans = _en_no_evidence()
    # markers and the endpoint token stay - other judges key on them
    assert "No indexed evidence matched this question" in ans
    assert "/v1/github/analyze" in ans


def test_japanese_reply_still_asks_the_administrator():
    ja = EchoModelAdapter().generate(
        GenerationRequest(
            system_prompt="", user_message="存在しない社名の決算は", data_context=""
        )
    ).text
    assert "現時点では十分な根拠がありません" in ja
    assert "管理者" in ja
