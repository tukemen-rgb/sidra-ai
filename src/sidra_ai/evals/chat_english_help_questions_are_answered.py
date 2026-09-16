"""Is an English 「what can you do?」 answered, or sent to the index wall?

C-1904. ``_HELP_QUERIES`` recognised Japanese meta-questions (and the bare word
「help」) but not the way an English speaker asks what this is or how to use it, so
「What can you do?」「who are you?」「how do I use this?」 fell through to retrieval
and came back with unrelated Japanese corpus fragments. The English sibling of
C-1901 (Japanese identity/help) and C-1902 (English greetings).

The fix adds the English phrasings and, following rule 6, answers in the
message's language: a Japanese help question keeps the Japanese reply (with the
live kind list), an English one gets an English reply. It stays a whole-message
match, so a real corpus question that shares a word (「how do I use the auth
module?」) is untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

ENGLISH_HELP_QUESTIONS: tuple[str, ...] = (
    "what can you do", "what do you do", "what can this do",
    "who are you", "what are you", "what is this tool",
    "how do i use this", "how do i use it", "how does this work",
    "help me",
)

#: Real English corpus questions that share a word but must stay questions.
NOT_HELP: tuple[str, ...] = (
    "What is the sales plan?",
    "how do I use the auth module?",
)

_JP_HELP = "索引済みリポジトリについてお答えします"
_WALL = "/v1/github/analyze"
_NO_EVIDENCE = "十分な根拠がありません"
_CJK = re.compile(r"[぀-ヿ㐀-鿿]")


@dataclass(frozen=True)
class EnglishHelpResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service() -> SidraService:
    root = Path(scratch_dir("sidra-c1904-"))
    return SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )


def evaluate_chat_english_help_questions_are_answered() -> EnglishHelpResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    service = _service()

    # --- (A) each English help question gets the help reply, in English ----
    for q in ENGLISH_HELP_QUESTIONS:
        r = service.chat(q)
        answer = r.get("answer") or ""
        english = bool(re.search(r"[A-Za-z]", answer)) and not _CJK.search(answer) \
            and _NO_EVIDENCE not in answer and _WALL not in answer
        add(r.get("refusal") == "help" and english,
            f"A: {q!r} -> refusal={r.get('refusal')!r}, english={english}")

    # --- (B) a Japanese help question still gets the Japanese reply --------
    for q in ("何ができる", "使い方を教えて"):
        r = service.chat(q)
        add(r.get("refusal") == "help" and _JP_HELP in (r.get("answer") or ""),
            f"B: {q!r} -> refusal={r.get('refusal')!r}")

    # --- (C) a real English corpus question is not treated as help --------
    for q in NOT_HELP:
        r = service.chat(q)
        add(r.get("refusal") != "help", f"C: {q!r} wrongly treated as help")

    total = len(ENGLISH_HELP_QUESTIONS) + 2 + len(NOT_HELP)
    return EnglishHelpResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "EnglishHelpResult",
    "evaluate_chat_english_help_questions_are_answered",
    "ENGLISH_HELP_QUESTIONS",
    "NOT_HELP",
]
