"""Deterministic, dependency-free backend.

This is the default so that ``pytest`` and ``sidra-api`` work on a clean
checkout with no model weights, no GPU, no network and no paid API. It does
not pretend to reason: it extracts the retrieved evidence and reports it with
citations, which is exactly what the pipeline plumbing needs to be tested
against.

Swap it for ``ollama``/``llama_cpp``/``transformers`` via
``SIDRA_MODEL_BACKEND`` once weights are available locally.
"""

from __future__ import annotations

import re

from sidra_ai.creation.evidence import plain_text
from sidra_ai.models.base import (
    GenerationRequest,
    GenerationResult,
    LocalModelAdapter,
    estimate_tokens,
)

#: A question containing any CJK character is treated as Japanese for the
#: canned no-evidence reply. Same ranges as retrieval tokenization.
_CJK = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")

#: Below this many characters a "sentence" is a label or list-marker
#: fragment (「D-CY4.」「A.」), not content a reader can act on.
_MIN_INFORMATIVE = 12

_BLOCK = re.compile(
    r"<<<SIDRA_DATA_BLOCK (?P<label>S\d+)>>>\n"
    r"source: (?P<citation>[^\n]*)\n"
    r"trust: (?P<trust>[^\n]*)\n"
    r"content:\n(?P<content>.*?)\n"
    r"<<<END_SIDRA_DATA_BLOCK (?P=label)>>>",
    re.DOTALL,
)


class EchoModelAdapter(LocalModelAdapter):
    """Summarizes retrieved blocks extractively, with citations."""

    backend = "echo"
    requires_paid_api = False

    def __init__(self, model: str = "sidra-local-v0", **options: object) -> None:
        super().__init__(model, **options)
        self.max_sentences_per_block = int(options.get("max_sentences_per_block", 2))

    def generate(self, request: GenerationRequest) -> GenerationResult:
        blocks = list(_BLOCK.finditer(request.data_context))

        if not blocks:
            question = request.user_message.strip()
            if _CJK.search(question):
                # SYSTEM_PROMPT rule 6 - born from the 2026-08-27 incident -
                # says a Japanese question gets a Japanese answer, and this
                # canned text was the one reply that ignored it (C-1202). It
                # must open with a marker `grounding._NO_EVIDENCE_MARKERS`
                # recognizes at sentence start, and every later sentence must
                # start with an advisory prefix (別の/確認), so the honest
                # abstention still *counts* as one in the grounding eval.
                text = (
                    "現時点では十分な根拠がありません。資料を索引した範囲では、"
                    "この質問へ答えられる内容が見つかりませんでした。"
                    "別の言い方で質問し直すか、対象リポジトリの取り込み"
                    "（POST /v1/github/analyze）を管理者に依頼してください。\n\n"
                    f"確認した質問: {question}"
                )
            else:
                text = (
                    "No indexed evidence matched this question. "
                    "Run POST /v1/github/analyze to ingest the repositories, or "
                    "rephrase the question.\n\n"
                    f"Question received: {question}"
                )
            return self._result(request, text, finish_reason="no_evidence")

        # The framing lines follow the question's language, same rule and
        # same reason as the no-evidence reply above (C-1202/C-1208): rule 6
        # holds for the successful path too, and this preamble opens every
        # answered Japanese question. The [S#] labels and excerpts between
        # them are untouched either way, so grounding's citation checks and
        # every excerpt-based judge read the same evidence.
        if _CJK.search(request.user_message):
            preamble = (
                "索引済みリポジトリの DATA から回答します"
                "（抜粋・ローカル生成・外部 API 不使用）。"
            )
            footer = "引用した出典: "
        else:
            preamble = (
                "Answering from indexed repository DATA "
                "(extractive; local backend, no external API)."
            )
            footer = "Cited sources: "

        lines = [preamble, ""]
        for match in blocks:
            excerpt = self._lead(match.group("content"))
            lines.append(f"[{match.group('label')}] {match.group('citation')}")
            lines.append(f"    {excerpt}")
            lines.append("")

        lines.append(
            footer
            + ", ".join(f"[{m.group('label')}] {m.group('citation')}" for m in blocks)
        )
        return self._result(request, "\n".join(lines).strip())

    # ------------------------------------------------------------------
    def _lead(self, content: str) -> str:
        # The corpus is Markdown, and a sentence-terminator split treats a
        # heading label (「## D-CY4.」) and a checkbox stub (「**A.」) as two
        # full sentences - the whole excerpt budget spent before any actual
        # content (C-1216). Flatten the markup the way generated documents
        # already do (C-1212; symbols only, every literal survives), and let
        # short fragments ride along without consuming a sentence slot.
        collapsed = plain_text(content)
        sentences = re.split(r"(?<=[.。!?！？])\s+", collapsed)
        take = 0
        informative = 0
        for sentence in sentences:
            take += 1
            if len(sentence.strip()) >= _MIN_INFORMATIVE:
                informative += 1
                if informative >= self.max_sentences_per_block:
                    break
        lead = " ".join(sentences[:take]).strip()
        return (lead[:400] + "...") if len(lead) > 400 else lead or "(empty)"

    def _result(
        self, request: GenerationRequest, text: str, finish_reason: str = "stop"
    ) -> GenerationResult:
        return GenerationResult(
            text=text,
            backend=self.backend,
            model=self.model,
            input_tokens_estimate=estimate_tokens(self.build_prompt(request)),
            output_tokens_estimate=estimate_tokens(text),
            finish_reason=finish_reason,
            metadata={"extractive": True, "cost_usd": 0.0},
        )
