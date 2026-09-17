"""Asked in English how to make something the product makes, does it answer?

C-1921, the English twin of C-1875. 「レポートの作り方を教えて」 gets a
``how_to_make`` reply that names what can be made and shows an example; but
"how do I make a report" / "how do I create a game" fell through to RAG and came
back with an unrelated indexed document. ``_how_to_make_kinds`` recognised only
Japanese cues (作り方, どうやって作る) and matched kinds by their Japanese labels,
so an English speaker's most natural phrasing missed - the same JP-only gap the
conversational-entry family closed for greetings/help/lists/delete/unsupported
creation (C-1902/1904/1906/1915/1919).

The fix adds English how-to-make cues and English kind keywords, and answers in
the request's language (rule 6). The boundary is unchanged: a corpus question
that names where to look ("...from the docs") stays a corpus question, and a
cue with no kind ("how does the build work") is not this question.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService, _how_to_make_kinds
from sidra_ai.config.settings import Settings
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: English "how do I make one" questions, each naming a kind the product makes.
ENGLISH_HOW_TO: tuple[str, ...] = (
    "how do I make a report",
    "how do I create a game",
    "how can I make a deck",
    "how do I make a gif",
    "how to make slides",
    "how do I make a 3d model",
)

#: Not this question: a corpus question that names where to look, a cue with no
#: kind, and an ops question. ``_how_to_make_kinds`` must return () for these.
NOT_HOW_TO: tuple[str, ...] = (
    "how do I make a report from the docs",
    "how does the build work",
    "how do I deploy the app",
    "what does the game loop do",
)

_WALL = "/v1/github/analyze"
_JP_MADE = "作れます"


@dataclass(frozen=True)
class HowToMakeEnglishResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service() -> SidraService:
    root = Path(scratch_dir("sidra-c1921-"))
    return SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )


def evaluate_chat_answers_how_to_make_in_english() -> HowToMakeEnglishResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    service = _service()
    registered = service.creation_router.registered_kinds()

    # (A) each English how-to-make question is answered in English, not walled.
    for q in ENGLISH_HOW_TO:
        r = service.chat(q)
        answer = r.get("answer") or ""
        english = any(c.isascii() and c.isalpha() for c in answer) \
            and _JP_MADE not in answer and _WALL not in answer
        add(r.get("refusal") == "how_to_make" and english,
            f"A: {q!r} -> refusal={r.get('refusal')!r}, english={english}: 「{answer[:120]}」")

    # (B) the English answer points the reader at how to actually ask, with an
    #     example of a real make request.
    r = service.chat("how do I make a report")
    add("for example" in (r.get("answer") or "").lower(),
        f"B: the English how-to answer has no example: 「{r.get('answer')}」")

    # (C) the Japanese phrasing still works (regression guard).
    for q in ("レポートの作り方を教えて", "ゲームの作り方は"):
        add(service.chat(q).get("refusal") == "how_to_make",
            f"C: Japanese {q!r} regressed")

    # (D) boundary: corpus/ops questions are not read as how-to-make.
    caught = [q for q in NOT_HOW_TO if _how_to_make_kinds(q, registered)]
    add(not caught, f"D: a non-how-to question was caught: {caught}")

    total = len(ENGLISH_HOW_TO) + 1 + 2 + 1
    return HowToMakeEnglishResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ENGLISH_HOW_TO",
    "NOT_HOW_TO",
    "HowToMakeEnglishResult",
    "evaluate_chat_answers_how_to_make_in_english",
]
