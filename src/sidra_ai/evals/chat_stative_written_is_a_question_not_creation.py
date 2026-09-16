"""Is 「どこに書いてある？」 a question, or misread as a request to write?

C-1899. ``_MAKE_VERBS`` holds the te-form 「書いて」 as a make cue, matched as a
substring. But 「書いてある」「書いている」「書いてる」「書いてます」 are that te-form
plus an existential/progressive auxiliary - "is written", a statement about
content that already exists - and 「どこ／何が」 is not in ``_QUESTION_MARKERS``,
so 「どこに書いてある？」 was classified as a creation request and answered
「制作のご依頼と受け取りましたが、この形式は作れません」. A plain question about the
corpus never reached the corpus.

The C-1837/C-1533 family: a making cue hiding inside a longer form that means
something else. The fix neutralises the stative 書いて/描いて forms before the
make-verb scan, so 「書いてある」 stops matching 「書いて」 - without touching a real
「レポートを書いて」, whose 書いて stands at the end of the request.

Both directions are checked: the stative questions must not be creation, and a
genuine 「…を書いて」 must still be. Two checks drive the whole service.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: 「書いてある/書いている」 forms - asking about existing content. None is a
#: request to write, so none may be routed to creation.
STATIVE_QUESTIONS: tuple[str, ...] = (
    "それはどこに書いてある？",
    "どこに書いてある？",
    "何て書いてある？",
    "そこに何が書いてあるの？",
    "書いてある内容を要約して",
    "設定はどこに書いてある",
    "コードに書いてる",
    "仕様書に書いていた",
)

#: Genuine 「…を書いて」 make requests: the te-form imperative stands at the end,
#: not before an auxiliary. These must stay creation (the format may still be
#: unsupported - that is a creation reply, not a question).
GENUINE_MAKE: tuple[str, ...] = (
    "レポートを書いて",
    "紹介文を書いて",
    "レポートを書いてください",
    "メモを書いておいて",
)


@dataclass(frozen=True)
class StativeWrittenResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_chat_stative_written_is_a_question_not_creation() -> StativeWrittenResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) a stative "is written" phrase is not a creation request -------
    for q in STATIVE_QUESTIONS:
        add(not detect_creation_intent(q).is_creation, f"A: read as creation: {q!r}")

    # --- (B) a genuine "write X" is still a creation request --------------
    for q in GENUINE_MAKE:
        add(detect_creation_intent(q).is_creation, f"B: not read as creation: {q!r}")

    # --- (C) end to end: a stative question is not answered with the
    #         "cannot make that format" creation refusal ---------------------
    root = Path(scratch_dir("sidra-c1899-"))
    service = SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )
    stative = service.chat("設定はどこに書いてある")
    ans = stative.get("answer") or ""
    add("制作のご依頼" not in ans and "この形式は作れません" not in ans,
        "C: a stative question got the creation 'cannot make that format' reply")

    # --- (D) and a genuine write request still reaches creation -----------
    made = service.chat("レポートを書いて")
    made_ans = made.get("answer") or ""
    add(bool(made.get("creation")) or "作りました" in made_ans,
        "D: a genuine 'write a report' no longer reaches creation")

    total = len(STATIVE_QUESTIONS) + len(GENUINE_MAKE) + 2
    return StativeWrittenResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "StativeWrittenResult",
    "evaluate_chat_stative_written_is_a_question_not_creation",
    "STATIVE_QUESTIONS",
    "GENUINE_MAKE",
]
