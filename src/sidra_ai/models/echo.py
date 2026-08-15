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

from sidra_ai.models.base import (
    GenerationRequest,
    GenerationResult,
    LocalModelAdapter,
    estimate_tokens,
)

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
            text = (
                "No indexed evidence matched this question. "
                "Run POST /v1/github/analyze to ingest the repositories, or "
                "rephrase the question.\n\n"
                f"Question received: {request.user_message.strip()}"
            )
            return self._result(request, text, finish_reason="no_evidence")

        lines = [
            "Answering from indexed repository DATA "
            "(extractive; local backend, no external API).",
            "",
        ]
        for match in blocks:
            excerpt = self._lead(match.group("content"))
            lines.append(f"[{match.group('label')}] {match.group('citation')}")
            lines.append(f"    {excerpt}")
            lines.append("")

        lines.append(
            "Cited sources: "
            + ", ".join(f"[{m.group('label')}] {m.group('citation')}" for m in blocks)
        )
        return self._result(request, "\n".join(lines).strip())

    # ------------------------------------------------------------------
    def _lead(self, content: str) -> str:
        collapsed = " ".join(content.split())
        sentences = re.split(r"(?<=[.。!?！？])\s+", collapsed)
        lead = " ".join(sentences[: self.max_sentences_per_block]).strip()
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
