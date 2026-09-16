"""Are 「あなたは誰？」「助けて」「どう使うの？」 answered, or sent to the index wall?

C-1901. ``_HELP_QUERIES`` recognised 「使い方」「何ができるの」「このアプリは何」 but
not the way people actually ask who this is, for help, or how to use it - so
「あなたは誰？」「君は誰」「助けて」「使い方がわからない」「どう使うの？」「何をして
くれるの？」「何が得意？」 all reached 「現時点では十分な根拠がありません…対象リポジ
トリの取り込みを管理者に依頼してください」. A person asking what the tool is was
told to ingest a repository.

The C-1796/C-1802 conversational-input family: input that is about the product
itself, not the corpus, must not fall to the no-evidence abstention. The fix
adds the missing whole-message phrasings to ``_HELP_QUERIES``; it stays a
whole-message match, so a real corpus query that merely contains 「使い方」 or
「何」 (「認証の使い方を教えて」) is untouched.

Both directions are checked, and two run the whole service so the detector
staying wired to the help reply is proven, not assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService, _is_help_query
from sidra_ai.config.settings import Settings
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: How people actually ask who this is / for help / how to use it. Each is a
#: whole-message meta question about the product, not the corpus.
IDENTITY_HELP_QUESTIONS: tuple[str, ...] = (
    "あなたは誰？",
    "あなたは何？",
    "君は誰",
    "きみは何ができる",
    "これは何のツール",
    "助けて",
    "助けてください",
    "使い方がわからない",
    "どう使うの？",
    "何をしてくれるの？",
    "何が得意？",
)

#: Real corpus questions that merely share a word. None may become a help reply.
NOT_HELP_QUESTIONS: tuple[str, ...] = (
    "認証の使い方を教えて",
    "このアプリの設計を教えて",
    "使い方のドキュメントを探して",
    "何が得意な言語かをドキュメントから調べて",
)


@dataclass(frozen=True)
class IdentityHelpResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_chat_identity_and_help_questions_are_answered() -> IdentityHelpResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) every identity/help phrasing is recognised -------------------
    for q in IDENTITY_HELP_QUESTIONS:
        add(_is_help_query(q), f"A: not recognised as help: {q!r}")

    # --- (B) no corpus question is mistaken for a help query --------------
    for q in NOT_HELP_QUESTIONS:
        add(not _is_help_query(q), f"B: wrongly recognised as help: {q!r}")

    # --- (C) end to end: an identity question is answered with the help
    #         reply, not the no-evidence abstention -------------------------
    root = Path(scratch_dir("sidra-c1901-"))
    service = SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )
    hit = service.chat("あなたは誰？")
    add(hit.get("refusal") == "help"
        and "十分な根拠がありません" not in (hit.get("answer") or ""),
        f"C: an identity question answered {hit.get('refusal')!r}")

    # --- (D) and a corpus question does not get the help reply ------------
    veto = service.chat("認証の使い方を教えて")
    add(veto.get("refusal") != "help",
        "D: a corpus question was answered as a help query")

    total = len(IDENTITY_HELP_QUESTIONS) + len(NOT_HELP_QUESTIONS) + 2
    return IdentityHelpResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "IdentityHelpResult",
    "evaluate_chat_identity_and_help_questions_are_answered",
    "IDENTITY_HELP_QUESTIONS",
    "NOT_HELP_QUESTIONS",
]
