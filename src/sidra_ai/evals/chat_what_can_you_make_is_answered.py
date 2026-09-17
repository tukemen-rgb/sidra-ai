"""Asked what it can make, does it say - or send the reader to ingest a repo?

C-1923. The help branch already answers with the product's capabilities:
「SIDRA は索引済みリポジトリについてお答えします。制作もでき、いま作れるのは
アート・スライド・…です」. But it only fired for a fixed set of help phrasings,
and 「何が作れますか」「作れるものは」「あなたは何が作れますか」 - the most direct
way to ask what the product can make - were not in it, so they fell to the
no-evidence wall that asks for a repository to be ingested. The product knows
the answer and refused to give it. (English "what can you make" happened to
land on the unsupported-creation decline, which lists the kinds but frames it as
a rejected request; routing it to help gives the right framing too.)

The fix adds the capability phrasings to ``_HELP_QUERIES`` so they reach the
help answer, in the request's language (rule 6). It stays a whole-message match,
so a real make request (「レースゲームを作って」) is untouched and still creates.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: Japanese ways to ask what the product can make.
JP_CAPABILITY: tuple[str, ...] = (
    "何が作れますか",
    "何が作れる",
    "何が作れるの",
    "作れるものは",
    "作れるものは何ですか",
    "あなたは何が作れますか",
    "どんなものが作れますか",
    "何を作れますか",
)
#: English ways to ask the same.
EN_CAPABILITY: tuple[str, ...] = (
    "what can you make",
    "what can you create",
)
#: A real make request must still create, not be swallowed as a help question.
NOT_CAPABILITY: tuple[str, ...] = (
    "レースゲームを作って",
    "犬のレポートを作って",
)

_WALL = "/v1/github/analyze"


@dataclass(frozen=True)
class WhatCanYouMakeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service() -> SidraService:
    root = Path(scratch_dir("sidra-c1923-"))
    return SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )


def evaluate_chat_what_can_you_make_is_answered() -> WhatCanYouMakeResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    service = _service()

    # (A) each Japanese capability question is answered by the help branch,
    #     which names what can be made, and is not sent to the wall.
    for q in JP_CAPABILITY:
        r = service.chat(q)
        answer = r.get("answer") or ""
        add(r.get("refusal") == "help" and "作れる" in answer and _WALL not in answer,
            f"A: {q!r} -> refusal={r.get('refusal')!r}: 「{answer[:110]}」")

    # (B) the English capability questions get the help answer in English.
    for q in EN_CAPABILITY:
        r = service.chat(q)
        answer = r.get("answer") or ""
        english = any(c.isascii() and c.isalpha() for c in answer) and "索引" not in answer
        add(r.get("refusal") == "help" and english,
            f"B: {q!r} -> refusal={r.get('refusal')!r}: 「{answer[:110]}」")

    # (C) a real make request still creates - it is not swallowed as help.
    for q in NOT_CAPABILITY:
        add(service.chat(q).get("refusal") != "help",
            f"C: {q!r} was wrongly treated as a help question")

    total = len(JP_CAPABILITY) + len(EN_CAPABILITY) + len(NOT_CAPABILITY)
    return WhatCanYouMakeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "JP_CAPABILITY",
    "EN_CAPABILITY",
    "NOT_CAPABILITY",
    "WhatCanYouMakeResult",
    "evaluate_chat_what_can_you_make_is_answered",
]
