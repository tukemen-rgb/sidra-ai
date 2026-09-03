"""C-1205: a subject the templates cannot draw must be admitted, not renamed.

「猫のゲームを作って」 chose the default fishing template and the summary
claimed 「「猫」を作りました」 - the subject-side twin of the genre lie the
summary already refuses (リズム型はまだ作れないため…). The caveat fires only
when the request named neither a template nor a genre and the title came
from the request; satisfied requests keep their uncaveated summary.
"""

from __future__ import annotations

import tempfile

import pytest

from sidra_ai.creation.games import detect_genre
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.creation.router import build_default_router


@pytest.fixture
def summarize():
    router = build_default_router(data_dir=tempfile.mkdtemp(prefix="c1205-"))

    def _run(message: str) -> str:
        return router.route(message, detect_creation_intent(message), []).summary

    return _run


def test_subject_requests_name_no_genre():
    """The branch keys off detect_genre: a subject request names none."""

    assert detect_genre("猫のゲームを作って") is None
    assert detect_genre("釣りゲームを作って") is not None
    assert detect_genre("シューティングゲームを作って") is not None


def test_subject_fallback_is_admitted(summarize):
    summary = summarize("猫のゲームを作って")
    assert "「猫」の題材を描く型はまだ無いため" in summary
    assert "題は「猫」のまま" in summary
    assert not summary.startswith("「猫」を作りました")


def test_named_template_keeps_plain_summary(summarize):
    summary = summarize("釣りゲームを作って")
    assert summary.startswith("「釣り」を作りました")
    assert "まだ無いため" not in summary


def test_default_title_request_keeps_plain_summary(summarize):
    summary = summarize("ゲームを作って")
    assert "まだ無いため" not in summary
    assert "まだ作れないため" not in summary


def test_genre_honesty_message_is_untouched(summarize):
    summary = summarize("リズムゲームを作って")
    assert "リズム型はまだ作れないため" in summary


def test_subject_honesty_eval_passes():
    from sidra_ai.evals.subject_honesty import evaluate_subject_honesty

    result = evaluate_subject_honesty()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5
