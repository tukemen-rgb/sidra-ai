"""C-1201: chat must say "no evidence" rather than answer from bigram glue.

The failure being pinned: BM25's CJK bigrams score cross-word glue
(「を教」「気は」 out of 「天気を教えて」), so a question whose subject the
corpus has never seen still fills ``top_k``, and the echo backend then
presents five unrelated excerpts as a cited answer with ``refused: false``.
Observed against the real corpus on 2026-09-03: 「天気を教えて」 answered
with marketing copy, 「会社の電話番号を教えて」 with AdSense setup steps.

The floor is deliberately narrow. It is applied at answer composition in
``SidraService.chat`` only: ranking, ``min_score`` and ``/v1/retrieve`` are
untouched, and a single subject-term hit anywhere in the retrieved evidence
keeps today's behavior exactly.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.evals.qa_honesty import PROBES, evaluate_qa_honesty
from sidra_ai.retrieval.search import (
    evidence_mentions_subject,
    subject_terms,
    tokenize,
)

REPOSITORY = "tukemen-rgb/site"

#: Glue-rich on purpose: shares 「を教」「教え」「はど」-shaped bigrams with
#: everyday questions while containing nothing about weather or phones.
GLUE_RICH = (
    "広告の方針を教えてください、と聞かれたら第三者 JS を載せない方針を"
    "案内する。運営コストはどうなっていますか、には実測値だけを出す。"
)


def _document(content: str, *, path: str = "docs/policy.md") -> Document:
    return Document(
        content=content,
        provenance=Provenance(
            source="github",
            repository=REPOSITORY,
            path=path,
            commit_sha="c" * 40,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="MIT",
        ),
    )


@pytest.fixture
def service(settings: Settings, store, gate) -> SidraService:
    return SidraService(settings, store=store, gate=gate)


# ------------------------------------------------------------ subject terms


def test_subject_terms_drop_glue_bigrams():
    assert subject_terms("天気を教えて") == ("天気",)


def test_subject_terms_keep_latin_katakana_and_kanji():
    terms = subject_terms("GAMEYARDのコストと方針")
    assert "gameyard" in terms
    assert "コス" in terms  # katakana bigram of コスト
    assert "方針" in terms
    assert all("の" not in term for term in terms)


def test_kana_only_question_has_no_subject_terms():
    assert subject_terms("どうしてですか") == ()


# ----------------------------------------------------- the evidence floor


def _chunk_of(content: str):
    document = _document(content)
    return type(
        "C", (), {"content": document.content, "provenance": document.provenance}
    )


def test_glue_only_overlap_is_not_evidence():
    assert not evidence_mentions_subject("天気を教えて", [_chunk_of(GLUE_RICH)])


def test_one_subject_hit_keeps_the_evidence():
    assert evidence_mentions_subject("広告の方針を教えて", [_chunk_of(GLUE_RICH)])


def test_unjudgeable_query_leaves_behavior_unchanged():
    """No subject terms means no verdict - never a refusal on glue grounds."""

    assert evidence_mentions_subject("どうしてですか", [_chunk_of(GLUE_RICH)])
    # Sanity: the chunk really does share tokens with such a question.
    assert set(tokenize("どうしてですか")) & set(tokenize(GLUE_RICH)) == set()


# ------------------------------------------------------- through /v1/chat


def test_offtopic_question_gets_the_no_evidence_answer(service: SidraService):
    service.store.add(_document(GLUE_RICH))

    result = service.chat("天気を教えて")

    assert result["refused"] is False
    assert result["citations"] == []
    # C-1202: a Japanese question gets the Japanese abstention, not the
    # English canned text with an internal API instruction.
    assert "根拠がありません" in result["answer"]
    assert "No indexed evidence" not in result["answer"]


def test_ontopic_question_still_answers_with_citations(service: SidraService):
    service.store.add(_document(GLUE_RICH))

    result = service.chat("広告の方針を教えて")

    assert result["refused"] is False
    assert result["citations"], "the floor must not eat answerable questions"
    assert "docs/policy.md" in {c["path"] for c in result["citations"]}


def test_follow_up_is_judged_with_its_carried_history(service: SidraService):
    """The history-retry query is the one whose subject terms count."""

    service.store.add(_document(GLUE_RICH))

    result = service.chat(
        "それはなぜ？", history=[("広告の方針を教えて", "第三者 JS は載せません")]
    )

    assert result["citations"], "history-carried subject must keep its evidence"


# ---------------------------------------------- C-1202: reply language


def test_japanese_no_evidence_reply_is_japanese_and_still_abstains(
    service: SidraService,
):
    from sidra_ai.evals.grounding import evaluate_grounding

    result = service.chat("会議室の予約方法を教えて")

    assert "No indexed evidence" not in result["answer"]
    assert "根拠がありません" in result["answer"]
    assert evaluate_grounding(result["answer"], result["citations"]).passed


def test_english_no_evidence_reply_stays_english(service: SidraService):
    result = service.chat("What is the deployment cadence?")

    assert "No indexed evidence matched" in result["answer"]


def test_no_evidence_language_eval_passes():
    from sidra_ai.evals.qa_honesty import evaluate_no_evidence_language

    result = evaluate_no_evidence_language()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 4


# ------------------------------------- C-1208: with-evidence framing


def test_japanese_answer_is_framed_in_japanese(service: SidraService):
    service.store.add(_document(GLUE_RICH))

    result = service.chat("広告の方針を教えて")

    assert "索引済みリポジトリの DATA から回答します" in result["answer"]
    assert "引用した出典" in result["answer"]
    assert "Answering from indexed" not in result["answer"]
    assert "Cited sources" not in result["answer"]
    # The evidence blocks themselves are untouched by the reframing.
    assert "[S1]" in result["answer"]


def test_english_answer_keeps_english_framing(service: SidraService):
    service.store.add(
        _document("The ads policy allows no third-party scripts on GAMEYARD pages.")
    )

    result = service.chat("What is the ads policy?")

    assert "Answering from indexed repository DATA" in result["answer"]
    assert "Cited sources:" in result["answer"]


def test_answer_language_eval_passes():
    from sidra_ai.evals.qa_honesty import evaluate_answer_language

    result = evaluate_answer_language()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


# ------------------------------------------------------------- the judge


def test_qa_honesty_eval_passes():
    result = evaluate_qa_honesty()
    assert result.failures == ()
    assert result.passed
    assert result.offtopic_total + result.ontopic_total == len(PROBES)
