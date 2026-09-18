"""Does an English greeting get a friendly reply, or the index wall?

C-1902. ``_GREETINGS`` was Japanese-only by an explicit scope decision, so an
English-speaking employee (a user C-0k names) typing 「hello」/「thanks」 fell
through to the no-evidence abstention - the English one that ends 「ask your
administrator to ingest the relevant repositories (POST /v1/github/analyze)」.
The most basic social opening read as a technical failure. This is the English
twin of C-1796, which fixed exactly this for Japanese.

The fix recognises English greetings and, following SYSTEM_PROMPT rule 6,
answers in the question's language: a Japanese greeting still gets the Japanese
reply, an English greeting now gets an English one. It stays a whole-message
match, so 「hello, what is the sales plan?」 (a real question that opens with a
greeting) is untouched and still answered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

ENGLISH_GREETINGS: tuple[str, ...] = (
    "hello", "hi", "hey", "good morning", "good evening",
    "thanks", "thank you", "hello there", "hi there",
)

#: A real English message that is not a bare greeting: it must still be answered
#: (or abstained) as a question, never swallowed as a greeting.
NOT_A_GREETING: tuple[str, ...] = (
    "What is the monetization plan?",
    "hello, what is the sales plan?",
)

_WALL = "/v1/github/analyze"
_JP_NO_EVIDENCE = "十分な根拠がありません"
_JP_GREETING = "ご挨拶"


@dataclass(frozen=True)
class EnglishGreetingResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service() -> SidraService:
    root = Path(scratch_dir("sidra-c1902-"))
    return SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )


def evaluate_chat_english_greeting_is_answered() -> EnglishGreetingResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    service = _service()

    # --- (A) each English greeting gets the greeting reply, in English -----
    for g in ENGLISH_GREETINGS:
        r = service.chat(g)
        answer = r.get("answer") or ""
        english = bool(re.search(r"[A-Za-z]", answer)) and _JP_NO_EVIDENCE not in answer \
            and _WALL not in answer and _JP_GREETING not in answer
        add(r.get("refusal") == "greeting" and english,
            f"A: {g!r} -> refusal={r.get('refusal')!r}, english={english}")

    # --- (B) a Japanese greeting still gets the Japanese greeting reply ----
    for g in ("こんにちは", "ありがとう"):
        r = service.chat(g)
        answer = r.get("answer") or ""
        add(r.get("refusal") == "greeting" and _JP_GREETING in answer,
            f"B: {g!r} -> refusal={r.get('refusal')!r}, jp_reply={_JP_GREETING in answer}")

    # --- (C) a real English question is not swallowed as a greeting --------
    for q in NOT_A_GREETING:
        r = service.chat(q)
        add(r.get("refusal") != "greeting", f"C: {q!r} wrongly treated as a greeting")

    total = len(ENGLISH_GREETINGS) + 2 + len(NOT_A_GREETING)
    return EnglishGreetingResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "EnglishGreetingResult",
    "evaluate_chat_english_greeting_is_answered",
    "ENGLISH_GREETINGS",
    "NOT_A_GREETING",
]
