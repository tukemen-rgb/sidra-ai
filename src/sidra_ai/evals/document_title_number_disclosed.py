"""Does a document disclose a title figure the evidence does not support?

C-1476. The module's rule - a number appears in the document only if it was
retrieved - held for the body but not the cover. ``_title_from`` copies the
request's subject onto the heading, so a request naming a figure
(「解約率30%の改善レポート」「2024年度の売上」) put that number in the title beside
the preamble's promise 「数字はすべて下の出典から」, while ``validate_document``
could not see it (its number check starts below the first heading). A headline
statistic nothing in the evidence supports then read as a sourced, verified
figure, and the document passed validation as ``usable``.

The fix discloses, in 「まだ埋まっていないこと」, that the title carries a number
the evidence does not confirm - without reprinting the digit, because a number
the evidence does not carry is exactly what the validator catches, so the honest
disclosure is *that* a figure went unconfirmed (the set-aside line's C-1281
choice). A title number that the evidence does carry - in a fact or a source
label - is left silent, as is a title with no number at all.

The checks build real ``generate_document`` outputs and read the markdown.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sidra_ai.creation.documents import generate_document, validate_document
from sidra_ai.creation.evidence import Fact, NUMBER

_NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)
_DISCLOSURE = "タイトルに含まれる数値は、索引した根拠では確認できませんでした"


def _md(request: str, facts: list[Fact], set_aside: int = 0) -> str:
    return generate_document(request, facts=facts, now=_NOW, set_aside=set_aside).markdown


@dataclass(frozen=True)
class DocTitleNumberResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_document_title_number_disclosed() -> DocTitleNumberResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- an unsourced headline statistic is disclosed ---
    stat_facts = [Fact("解約率は改善した。", "docs/churn.md")]
    stat = _md("解約率30%の改善レポートを作って", stat_facts)
    add(_DISCLOSURE in stat, "stat: unsourced 30% in title not disclosed")
    # the disclosure names no digit (it must not itself be a fabricated number)
    disclosure_line = next((ln for ln in stat.splitlines() if _DISCLOSURE in ln), "")
    add(not NUMBER.findall(disclosure_line), "stat: disclosure line reprinted a digit")
    # the document still validates - the fix did not smuggle a number into the body
    add(validate_document(generate_document("解約率30%の改善レポートを作って",
                                            facts=stat_facts, now=_NOW),
                          stat_facts)["usable"],
        "stat: document no longer usable after disclosure")

    # --- an unsourced year in the title is disclosed too ---
    year = _md("2024年度の売上レポートを作って", [Fact("売上は前年より伸びた。", "docs/sales.md")])
    add(_DISCLOSURE in year, "year: unsourced 2024 in title not disclosed")

    # --- a title number the evidence carries is left silent ---
    in_text = _md("第3四半期の進捗レポートを作って", [Fact("第3四半期は完了した。", "docs/status.md")])
    add(_DISCLOSURE not in in_text, "in-text: title number in a fact wrongly disclosed")
    # via the source label (PR-17.md) - the validator counts labels, so does this
    via_label = _md("17番の課題レポートを作って", [Fact("認証まわりを直した。", "docs/PR-17.md")])
    add(_DISCLOSURE not in via_label, "label: title number in a source label wrongly disclosed")

    # --- a title with no number is silent ---
    no_num = _md("競合分析のレポートを作って", [Fact("競合Aは値下げした。", "docs/market.md")])
    add(_DISCLOSURE not in no_num, "no-number: silent title wrongly disclosed")

    # --- an empty skeleton with a numbered title still discloses (no evidence) ---
    empty = _md("2025年度の計画を作って", [])
    add(_DISCLOSURE in empty, "empty: numbered title with no evidence not disclosed")

    # --- set-aside and title disclosure coexist, both present ---
    both = _md("解約率30%の改善レポートを作って", stat_facts, set_aside=2)
    add("依頼と主題が重ならない" in both and _DISCLOSURE in both,
        "coexist: set-aside and title disclosure not both shown")

    # --- a fully sourced numbered body is untouched (no disclosure, usable) ---
    sourced_facts = [Fact("完了タスクは 42 件だった。", "docs/status.md")]
    sourced = generate_document("進捗レポートを作って", facts=sourced_facts, now=_NOW)
    add(_DISCLOSURE not in sourced.markdown
        and validate_document(sourced, sourced_facts)["usable"],
        "sourced: a sourced-number body was disturbed")

    total = 10
    return DocTitleNumberResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DocTitleNumberResult", "evaluate_document_title_number_disclosed"]
