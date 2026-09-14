"""Does a help question get an overview, not a corpus-miss abstention?

C-1802. 「使い方を教えて」「何ができる」「ヘルプ」 ask what the product is or how to
use it - not a corpus query. They fell through to retrieval and got the
no-evidence abstention that names 「POST /v1/github/analyze」, the worst reply for
someone actively asking for help. A bare meta question now gets a friendly
``refusal == "help"`` that says what SIDRA does (drawn from the live generator
registry), joining empty/ambiguous/unnamed/greeting/revision_target. A real
question, or one that merely contains 「使い方」, is untouched.

The checks drive the real ``SidraService.chat`` over the echo backend.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.evals.scratch import scratch_dir

_NO_EVIDENCE = "現時点では十分な根拠がありません"
_ENDPOINT = "/v1/github/analyze"


@dataclass(frozen=True)
class ChatHelpResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service():
    from pathlib import Path

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    tmp = Path(scratch_dir(prefix="chat-help-"))
    return SidraService(Settings(data_dir=str(tmp / "sidra")))


def evaluate_chat_help_query_is_answered_not_missed() -> ChatHelpResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    svc = _service()

    howto = svc.chat("使い方を教えて")
    punct = svc.chat("使い方を教えて。")             # trailing punctuation, still help
    question = svc.chat("火星の天気を教えて")          # a real question
    compound = svc.chat("使い方のドキュメントを探して")  # a real query that contains 「使い方」

    # --- (A) a bare help question is recognised as one -------------------
    add(howto.get("refusal") == "help",
        f"A: 「使い方を教えて」 was not handled as help (refusal={howto.get('refusal')!r})")
    # --- (B) the reply is not the corpus-miss abstention ----------------
    add(_NO_EVIDENCE not in howto.get("answer", "") and _ENDPOINT not in howto.get("answer", ""),
        "B: the help reply is the no-evidence abstention (names the endpoint)")
    # --- (C) the reply says what SIDRA does -----------------------------
    add("索引済みリポジトリ" in howto.get("answer", ""),
        "C: the help reply does not say what SIDRA does")
    # --- (D) trailing punctuation does not defeat the match -------------
    add(punct.get("refusal") == "help",
        f"D: 「使い方を教えて。」 was not handled as help (refusal={punct.get('refusal')!r})")
    # --- (E) a real question is not mistaken for a help query -----------
    add(question.get("refusal") != "help",
        "E: a real question was wrongly handled as a help query")
    # --- (F) a query that only contains 「使い方」 stays a query ----------
    add(compound.get("refusal") != "help",
        "F: 「使い方のドキュメントを探して」 was wrongly swallowed as a help query")

    total = 6
    return ChatHelpResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ChatHelpResult",
    "evaluate_chat_help_query_is_answered_not_missed",
]
