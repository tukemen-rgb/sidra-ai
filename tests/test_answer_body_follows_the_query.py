"""C-1825: the extractive answer body shows the sentence that answers the query.

The citation excerpt was made query-relevant (C-1782); the answer body itself
(``_lead``) still showed the chunk's opening sentences, so "What is the default
port?" answered with the language/dependency sentences and the answering "The
default port is 8080" appeared only in the excerpt below. ``_lead`` now opens the
answer on the sentence best matching the query, and falls back to the opening
when nothing matches, so ordinary answers are unchanged.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.gate import GatePolicy, SecurityGate
from sidra_ai.evals.answer_body_follows_the_query import (
    evaluate_answer_body_follows_the_query,
)

_EN = (
    "The service is written in Python and packaged as a wheel. "
    "It depends on FastAPI and uvicorn for serving. "
    "The default port is 8080 unless overridden. "
    "Logging goes to stdout in JSON."
)
_JP = (
    "このサービスはPythonで書かれています。"
    "FastAPIとuvicornに依存します。"
    "デフォルトのポートは8080です。"
    "ログはJSONで標準出力に出ます。"
)


def _answer(content: str, query: str) -> str:
    repo = "acme/app"
    gate = SecurityGate(GatePolicy(), allowed_repositories=(repo,))
    store = DocumentStore(gate)
    prov = Provenance(
        source="github", repository=repo, path="docs/run.md", commit_sha="abc1234",
        timestamp=datetime.now(timezone.utc), source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO, license="proprietary",
    )
    store.add(Document(content=content, provenance=prov))
    service = SidraService(
        Settings(data_dir=tempfile.mkdtemp()),
        model=EchoModelAdapter(), store=store, gate=gate,
    )
    return str((service.chat(query) or {}).get("answer") or "")


def test_answer_body_follows_query_eval_passes():
    result = evaluate_answer_body_follows_the_query()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


def test_later_sentence_answers_the_question():
    answer = _answer(_EN, "What is the default port?")
    assert "8080" in answer
    assert "default port" in answer


def test_later_sentence_answers_in_japanese():
    assert "8080" in _answer(_JP, "デフォルトのポートは何番ですか")


def test_opening_question_keeps_the_opening_and_does_not_overreach():
    answer = _answer(_EN, "What language is the service written in?")
    assert "Python" in answer
    # relevance must not drag in the unrelated later port sentence
    assert "8080" not in answer
