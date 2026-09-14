"""Does a bare greeting get a friendly reply, not a corpus-miss abstention?

C-1795. A message that is only a greeting or thanks (「こんにちは」「ありがとう」)
is not a question, but ``chat`` sent it through retrieval like any query and,
finding nothing, returned the no-evidence abstention - 「現時点では十分な根拠が
ありません…（POST /v1/github/analyze）を管理者に依頼してください」. So the most
common opening message a person types gets a technical failure that names an
API endpoint. The blank-message path already recognises a content-free input
and asks back (C-1515); a bare greeting is the same case. It now gets its own
friendly refusal (``refusal == "greeting"``), joining empty/ambiguous/unnamed
as a not-a-failure conversational reply. A greeting that opens a real question
(「こんにちは、売上を教えて」) is still answered as the question it is.

The checks drive the real ``SidraService.chat`` over the echo backend.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.evals.scratch import scratch_dir

_NO_EVIDENCE = "現時点では十分な根拠がありません"
_ENDPOINT = "/v1/github/analyze"


@dataclass(frozen=True)
class ChatGreetingResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service():
    from pathlib import Path

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

    tmp = Path(scratch_dir(prefix="chat-greeting-"))
    repository = "tukemen-rgb/sidra-ai"
    settings = Settings(allowed_repositories=(repository,), data_dir=str(tmp / "sidra"))
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=(repository,),
        quarantine_store=QuarantineStore(tmp / "quarantine.jsonl"),
    )
    return SidraService(settings, store=DocumentStore(gate), gate=gate)


def evaluate_chat_greeting_is_greeted_not_missed() -> ChatGreetingResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    svc = _service()

    hello = svc.chat("こんにちは")
    thanks = svc.chat("ありがとうございます。")   # trailing punctuation, still a greeting
    morning = svc.chat("おはよう")
    question = svc.chat("サイトのリポジトリについて教えて")
    compound = svc.chat("こんにちは、売上を教えて")  # a real question that opens with a greeting

    # --- (A) a bare greeting is recognised as one ------------------------
    add(hello.get("refusal") == "greeting",
        f"A: 「こんにちは」 was not handled as a greeting (refusal={hello.get('refusal')!r})")
    # --- (B) the greeting reply is not the corpus-miss abstention ---------
    add(_NO_EVIDENCE not in hello.get("answer", "") and _ENDPOINT not in hello.get("answer", ""),
        "B: the greeting reply is the no-evidence abstention (names the endpoint)")
    # --- (C) trailing punctuation does not defeat the match --------------
    add(thanks.get("refusal") == "greeting",
        f"C: 「ありがとうございます。」 was not handled as a greeting (refusal={thanks.get('refusal')!r})")
    # --- (D) a real question is not mistaken for a greeting --------------
    add(question.get("refusal") != "greeting",
        "D: a real question was wrongly handled as a greeting")
    # --- (E) a greeting-prefixed real question stays a question ----------
    add(compound.get("refusal") != "greeting",
        "E: 「こんにちは、売上を教えて」 was wrongly swallowed as a greeting")
    # --- (F) another greeting variant is recognised too -----------------
    add(morning.get("refusal") == "greeting",
        f"F: 「おはよう」 was not handled as a greeting (refusal={morning.get('refusal')!r})")

    total = 6
    return ChatGreetingResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ChatGreetingResult",
    "evaluate_chat_greeting_is_greeted_not_missed",
]
