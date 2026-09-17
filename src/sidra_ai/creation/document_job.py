"""The document generator as the router sees it.

Same split as every other kind; the summary reports the validator's verdict
and how much of the document is still the owner's to fill, because "書けた"
and "使える" are different claims and the second is the one that matters.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.models.echo import _reply_in_japanese

from sidra_ai.creation.documents import (
    CONTENT_SECTIONS,
    generate_document,
    requested_format,
    save_document,
    validate_document,
)
from sidra_ai.creation.empty import empty_notice
from sidra_ai.creation.evidence import Fact, on_topic, subject_unmatched
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
        # C-1532: whether the filter kept everything because it could not
        # find the subject anywhere, as opposed to because everything was
        # about it. Same facts either way; a different sentence beside them.
        unmatched = subject_unmatched(message, list(retrieved or []))
        document = generate_document(
            message, facts=facts, set_aside=len(aside), subject_unmatched=unmatched
        )
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
        # C-1935: which language this reply takes, from the product's own
        # rule (C-1929 through C-1934). Sixth and last caller of the same one
        # call - deck and document were the pair left, because the refusal
        # they share lives in `empty.py` rather than in either of them.
        in_japanese = _reply_in_japanese(message)
        notice = empty_notice(
            blank=len(hollow),
            total=len(CONTENT_SECTIONS),
            facts_available=len(facts),
            in_japanese=in_japanese,
        )
        if verdict["usable"] and notice:
            summary = notice
        elif verdict["usable"]:
            blanks = len(verdict["unfilled"])
            # Said out loud: a document quietly shorter than the evidence
            # behind it is its own kind of dishonesty, and the operator is
            # the one who can tell whether the request was too narrow.
            put_down = (
                (
                    f"（依頼と主題が重ならない根拠 {len(aside)} 件は載せていません）"
                    if in_japanese
                    else f"({len(aside)} passages that do not overlap the "
                         "subject are left out.) "
                )
                if aside
                else ""
            )
            if unmatched:
                # C-1532: 「根拠 N 件」 was counted straight off top_k, so a
                # subject the corpus has never heard of still produced a
                # confident number - the deck, asked the same thing, left
                # its slides blank and said which. The count is not wrong
                # about how many passages are in the file; it is wrong about
                # what they are evidence for, so it is not what leads.
                summary = (
                    (
                        f"「{document.title}」について索引に根拠は見つかりませんでした。"
                        f"レポートの形にはしましたが、載っている {verdict['sources']} 件は"
                        "検索が返した資料そのままで、主題に触れていません"
                        "（文書の冒頭にもそう書いています）。"
                        "主題を含む資料を取り込むか、依頼の言い方を変えてお試しください。"
                    )
                    if in_japanese
                    else (
                        f"No grounds for \u201c{document.title}\u201d were found "
                        "in the index. It has been put into the shape of a "
                        f"report, but the {verdict['sources']} passages in it are "
                        "whatever the search returned and do not touch the "
                        "subject (the document says so at the top too). Import "
                        "documents that contain the subject, or try wording the "
                        "request differently."
                    )
                )
            else:
                summary = (
                    (
                        f"「{document.title}」のレポートを作りました"
                        f"（根拠 {verdict['sources']} 件、"
                        f"社長が埋める欄 {blanks} 箇所）。"
                        f"{put_down}"
                        "Markdown なのでそのまま編集・貼り付けできます。"
                    )
                    if in_japanese
                    else (
                        f"Made a report on \u201c{document.title}\u201d "
                        f"({verdict['sources']} grounds, {blanks} fields for the "
                        f"owner to fill in). {put_down}"
                        "It is Markdown, so it can be edited and pasted as is."
                    )
                )
        else:
            summary = (
                (
                    f"「{document.title}」のレポートを作りましたが、検証に落ちています: "
                    + "、".join(str(f) for f in verdict["failures"])
                )
                if in_japanese
                else (
                    f"Made a report on \u201c{document.title}\u201d, but it "
                    "fails validation: "
                    + ", ".join(str(f) for f in verdict["failures"])
                )
            )
        # C-1834: the document generator only writes Markdown. When the request
        # named a file format it cannot produce (「…をWordで」/PDF/Excel), say so -
        # the document twin of the deck's pptx notice (C-1465). The generic
        # 「Markdown なので…」 line above names the output but never that the asked
        # format was not made, so a reader who wanted Word believed they got it.
        fmt = requested_format(message)
        if fmt:
            summary = summary.rstrip() + (
                f"なお {fmt} 形式では作れないため、Markdown で保存しています。"
                if in_japanese
                else f" {fmt} cannot be produced, so this is saved as Markdown."
            )
        return CreationOutcome(
            kind=intent.kind,
            handled=True,
            summary=summary,
            artifact_path=str(path),
            details={
                "title": document.title,  # C-1830
                "usable": verdict["usable"],
                "unfilled": verdict["unfilled"],
                "sources": verdict["sources"],
                "off_topic_facts": len(aside),
                # C-1532: the filter saw the subject and no fact carried it.
                "subject_unmatched": unmatched,
                # True when no section evidence fills came out with anything
                # in it - the file exists and has nothing to read (C-1128).
                "empty": bool(notice),
            },
        )

    return generate


__all__ = ["build_document_generator"]
