"""The document generator as the router sees it.

Same split as every other kind; the summary reports the validator's verdict
and how much of the document is still the owner's to fill, because "書けた"
and "使える" are different claims and the second is the one that matters.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.creation.documents import (
    CONTENT_SECTIONS,
    generate_document,
    save_document,
    validate_document,
)
from sidra_ai.creation.empty import empty_notice
from sidra_ai.creation.evidence import Fact, on_topic
from sidra_ai.creation.intent import CreationIntent
from sidra_ai.creation.router import CreationOutcome


def build_document_generator(data_dir: str | Path):
    def generate(
        message: str,
        intent: CreationIntent,
        retrieved: list[Fact] | None = None,
    ) -> CreationOutcome:
        # C-1403: the same floor the answer path has had since C-1201, one
        # level along. Retrieval fills top_k on cross-word glue, and a
        # document is where that shows worst - jam-making steps printed
        # under 「わかっていること」 with a source label beside them, which
        # is the shape a reader trusts most. Facts that share no subject
        # term with the request are set aside rather than printed.
        facts, aside = on_topic(message, list(retrieved or []))
        document = generate_document(message, facts=facts)
        verdict = validate_document(document, facts)
        path = save_document(document, data_dir)
        # C-1128: 「レポートを作りました（根拠 0 件、社長が埋める欄 3 箇所）」
        # was the sentence beside a file with no sentence in it. Counted over
        # the sections evidence can fill, which is the load-bearing part: a
        # report is *never* short of 「まだ埋まっていないこと」, so measuring
        # against all four SECTIONS gives 3-of-4 for a report with nothing in
        # it and the notice never fires. Filtering `hollow` alone would not
        # have mattered - both ends move together - and saying so is the
        # difference between a checked reason and a plausible one.
        hollow = [name for name in document.unfilled if name in CONTENT_SECTIONS]
        notice = empty_notice(
            blank=len(hollow),
            total=len(CONTENT_SECTIONS),
            facts_available=len(facts),
        )
        if verdict["usable"] and notice:
            summary = notice
        elif verdict["usable"]:
            blanks = len(verdict["unfilled"])
            # Said out loud: a document quietly shorter than the evidence
            # behind it is its own kind of dishonesty, and the operator is
            # the one who can tell whether the request was too narrow.
            put_down = (
                f"（依頼と主題が重ならない根拠 {len(aside)} 件は載せていません）"
                if aside
                else ""
            )
            summary = (
                f"「{document.title}」のレポートを作りました"
                f"（根拠 {verdict['sources']} 件、社長が埋める欄 {blanks} 箇所）。"
                f"{put_down}"
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
                "off_topic_facts": len(aside),
                # True when no section evidence fills came out with anything
                # in it - the file exists and has nothing to read (C-1128).
                "empty": bool(notice),
            },
        )

    return generate


__all__ = ["build_document_generator"]
