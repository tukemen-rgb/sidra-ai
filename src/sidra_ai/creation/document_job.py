"""The document generator as the router sees it.

Same split as every other kind; the summary reports the validator's verdict
and how much of the document is still the owner's to fill, because "書けた"
and "使える" are different claims and the second is the one that matters.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.creation.documents import generate_document, save_document, validate_document
from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.intent import CreationIntent
from sidra_ai.creation.router import CreationOutcome


def build_document_generator(data_dir: str | Path):
    def generate(
        message: str,
        intent: CreationIntent,
        retrieved: list[Fact] | None = None,
    ) -> CreationOutcome:
        facts = list(retrieved or [])
        document = generate_document(message, facts=facts)
        verdict = validate_document(document, facts)
        path = save_document(document, data_dir)
        if verdict["usable"]:
            blanks = len(verdict["unfilled"])
            summary = (
                f"「{document.title}」のレポートを作りました"
                f"（根拠 {verdict['sources']} 件、社長が埋める欄 {blanks} 箇所）。"
                "Markdown なのでそのまま編集・貼り付けできます。"
            )
        else:
            summary = (
                f"「{document.title}」のレポートを作りましたが、検証に落ちています: "
                + "、".join(str(f) for f in verdict["failures"])
            )
        return CreationOutcome(
            kind=intent.kind,
            handled=True,
            summary=summary,
            artifact_path=str(path),
            details={
                "usable": verdict["usable"],
                "unfilled": verdict["unfilled"],
                "sources": verdict["sources"],
            },
        )

    return generate


__all__ = ["build_document_generator"]
