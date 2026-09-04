"""What a generator says when every content section came out blank.

C-1128. A deck of four blank slides and a report with nothing under
「わかっていること」 are honest *artifacts* - the blanks are visible, labelled,
and the owner can fill them. The sentence beside them was not honest.
「「進捗報告」を 4 枚で作りました」 is the headline of an accomplishment, and
what happened was that nothing usable was retrieved and an empty frame was
printed. The frame may still be written to disk; the summary must not call
it a result.

The cause is reported, not assumed. "The index had nothing" and "plenty was
retrieved and none of it fit a section" produce the identical blank artifact
and need different next steps from the owner - import documents, or ask
differently - so the line names the one that actually happened rather than
the one that is easier to word.
"""

from __future__ import annotations

#: The headline. Deliberately not 「作りました」: every other summary in the
#: product opens by naming what was made, and this is the one case where
#: nothing was.
EMPTY_HEADLINE = "中身のある資料を作れませんでした。"

#: Nothing reached the generator at all.
EMPTY_INDEX = "索引にこの依頼の根拠がありません。資料を取り込んでからもう一度どうぞ。"

#: Evidence arrived and no section would take it.
EMPTY_UNMATCHED = (
    "根拠 {n} 件は届きましたが、どの欄にも当てはまりませんでした。"
    "依頼の言い方を変えるか、資料を足してからもう一度どうぞ。"
)

#: Said after the cause, so the owner knows the file exists without the
#: sentence ever implying the file is worth anything.
EMPTY_KEPT = "枠だけの下書きは保存してあります。"


def empty_notice(*, blank: int, total: int, facts_available: int) -> str:
    """The line to lead with, or ``""`` when the artifact has content.

    ``blank``/``total`` count *content* sections only. A section that is
    blank by construction - a report's 「まだ埋まっていないこと」 - is not
    evidence of anything and must not be passed in, or every document ever
    generated would read as empty.
    """

    if total <= 0 or blank < total:
        return ""
    cause = EMPTY_INDEX if facts_available <= 0 else EMPTY_UNMATCHED.format(n=facts_available)
    return f"{EMPTY_HEADLINE}{cause}{EMPTY_KEPT}"


__all__ = ["EMPTY_HEADLINE", "EMPTY_INDEX", "EMPTY_KEPT", "EMPTY_UNMATCHED", "empty_notice"]
