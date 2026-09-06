"""Does the saved report disclose that evidence was set aside as off-topic?

C-1281: the document generator drops facts that share no subject term with the
request (C-1403, so jam-recipe passages do not land in a weekly report). The
chat summary says so - 「（依頼と主題が重ならない根拠 N 件は載せていません）」-
but the summary is shown once and the ``.md`` file is the artifact that is
saved, edited and forwarded. The file disclosed nothing, so a report that had
quietly left out evidence read as the complete sourced picture it was not.

The file now discloses the withholding in 「まだ埋まっていないこと」 whenever any
fact was set aside, and stays silent when none was. No count is printed - a
digit that names nothing in the evidence is what ``validate_document`` catches
as a fabricated number - so the disclosure is words, and the document stays
usable.

Drives the real ``build_document_generator`` (the router's generator) for the
file, and ``generate_document``/``validate_document`` for the property, over a
request that mixes an on-topic fact with an off-topic one.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

_DISCLOSURE = "載せていません"

#: A launch-progress request. The bug fact shares no subject term with it, so
#: C-1403 sets it aside; the registration fact stays.
_REQUEST = "新機能ローンチの週次進捗レポートを作って"


def _facts():
    from sidra_ai.creation.evidence import Fact

    return [
        Fact("新機能ローンチの登録数は初週で 1,240 件に達した。", "r:docs/launch.md"),
        Fact("未対応の不具合は 3 件が残っており、来週の対応を予定。", "r:docs/bugs.md"),
    ]


def _on_topic_facts():
    from sidra_ai.creation.evidence import Fact

    return [
        Fact("新機能ローンチの登録数は初週で 1,240 件に達した。", "r:docs/launch.md"),
        Fact("新機能ローンチの週次進捗は順調に推移している。", "r:docs/status.md"),
    ]


@dataclass(frozen=True)
class DocumentSetAsideResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _saved_markdown(request: str, facts) -> tuple[str, dict]:
    """Run the router's document generator and read the file it saved."""
    from sidra_ai.creation.document_job import build_document_generator
    from sidra_ai.creation.intent import detect_creation_intent

    tmp = tempfile.mkdtemp(prefix="doc-aside-")
    generate = build_document_generator(tmp)
    intent = detect_creation_intent(request)
    out = generate(request, intent, list(facts))
    return Path(out.artifact_path).read_text(encoding="utf-8"), {
        "summary": out.summary,
        "off_topic_facts": (out.details or {}).get("off_topic_facts"),
    }


def evaluate_document_discloses_set_aside_evidence() -> DocumentSetAsideResult:
    from sidra_ai.creation.documents import generate_document, validate_document

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # 1: the saved file discloses the withholding when a fact was set aside.
    md_mixed, meta = _saved_markdown(_REQUEST, _facts())
    add(meta["off_topic_facts"] == 1,
        f"fixture did not set aside a fact (off_topic={meta['off_topic_facts']})")
    add(_DISCLOSURE in md_mixed, "saved file does not disclose the set-aside evidence")

    # 2: the disclosure sits in 「まだ埋まっていないこと」, not scattered.
    if "## まだ埋まっていないこと" in md_mixed and "## 出典" in md_mixed:
        section = md_mixed.split("## まだ埋まっていないこと", 1)[1].split("## 出典", 1)[0]
        add(_DISCLOSURE in section, "disclosure is not in 「まだ埋まっていないこと」")
    else:
        failures.append("report is missing its sections")

    # 3: the chat summary still discloses too (the fix adds to the file, does
    #    not move the disclosure off the summary).
    add(_DISCLOSURE in meta["summary"], "summary no longer discloses the set-aside")

    # 4: with every fact on-topic, nothing is set aside and the file does NOT
    #    invent a disclosure.
    md_clean, meta_clean = _saved_markdown(_REQUEST, _on_topic_facts())
    add(meta_clean["off_topic_facts"] == 0,
        f"on-topic fixture set a fact aside (off_topic={meta_clean['off_topic_facts']})")
    add(_DISCLOSURE not in md_clean, "file discloses a set-aside when none happened")

    # 5: the disclosure introduces no fabricated number - the document stays
    #    usable through the same validator the report is judged by - and
    #    set_aside=0 leaves the document exactly as before. Guarded so that
    #    code lacking the parameter (the pre-fix state this metric measures)
    #    scores these as failed rather than crashing the whole run.
    try:
        doc = generate_document(_REQUEST, facts=[_facts()[0]], set_aside=1)
        verdict = validate_document(doc, [_facts()[0]])
        add(_DISCLOSURE in doc.markdown,
            "generate_document(set_aside>0) omits the disclosure")
        add(verdict["usable"],
            f"disclosure made the document unusable: {verdict['failures']}")
        doc0 = generate_document(_REQUEST, facts=[_facts()[0]], set_aside=0)
        add(_DISCLOSURE not in doc0.markdown,
            "generate_document(set_aside=0) still adds the disclosure")
    except TypeError as exc:
        failures.append(f"generate_document has no set_aside parameter: {exc}")
        failures.append("generate_document(set_aside>0) unusable to test")
        failures.append("generate_document(set_aside=0) unusable to test")

    total = 9
    return DocumentSetAsideResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "DocumentSetAsideResult",
    "evaluate_document_discloses_set_aside_evidence",
]
