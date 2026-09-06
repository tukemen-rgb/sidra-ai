"""Does the English no-evidence reply route ingestion through the admin?

C-1269: with nothing indexed, an English question got
「No indexed evidence matched this question. Run POST /v1/github/analyze to
ingest the repositories, or rephrase the question.」 - a raw internal HTTP call
handed to the reader as their own imperative. The Japanese reply for the same
state says 「…取り込み（POST /v1/github/analyze）を管理者に依頼してください」,
framing the ingestion as an administrator's job. A general user, English or not,
cannot POST from a chat box; the two languages should agree that ingestion is
the administrator's action, not the reader's.

The endpoint token and the opening markers stay - other judges key on them
(``creation_unbuildable_declined`` uses ``/v1/github/analyze`` as the tell of
this Q&A wall, ``answer_language_defaults_japanese`` on the markers). Only the
English framing changes: the ask goes to the administrator, and the reader is no
longer told to run the endpoint themselves.

Measured through the real reply path (EchoModelAdapter, no data blocks).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: English questions: each lands on the no-evidence branch (nothing indexed).
_EN_QS: tuple[str, ...] = (
    "how do I reset my password",
    "what is the quarterly revenue",
    "who is the CEO",
)

#: Japanese questions: the regression guard - they already ask the admin.
_JA_QS: tuple[str, ...] = (
    "存在しない社名の決算は",
    "パスワードの再設定手順は",
)

_EN_MARKER = "No indexed evidence matched this question"
_JA_MARKER = "現時点では十分な根拠がありません"
_ENDPOINT = "/v1/github/analyze"

#: A reader being told to fire the endpoint themselves - the defect.
_USER_IMPERATIVE = re.compile(
    r"\b(run|execute|call|invoke|hit|send|do)\b[^.]*?" + re.escape(_ENDPOINT),
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NoEvidenceEnglishAdminFramedResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _no_evidence_answer(message: str) -> str:
    from sidra_ai.models.base import GenerationRequest
    from sidra_ai.models.echo import EchoModelAdapter

    return EchoModelAdapter().generate(
        GenerationRequest(system_prompt="", user_message=message, data_context="")
    ).text


def evaluate_no_evidence_english_admin_framed() -> NoEvidenceEnglishAdminFramedResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for q in _EN_QS:
        ans = _no_evidence_answer(q)
        first = ans.splitlines()[0] if ans else ""
        # 1: still reads as a no-evidence reply.
        add(_EN_MARKER in ans, f"EN {q!r}: opening marker missing in 「{first}」")
        # 2: ingestion is framed as an administrator's job.
        add("administrator" in ans.lower(),
            f"EN {q!r}: does not ask an administrator in 「{first}」")
        # 3: the reader is not told to run the endpoint themselves.
        add(_USER_IMPERATIVE.search(ans) is None,
            f"EN {q!r}: hands the reader a run-the-endpoint imperative in 「{first}」")
        # 4: the endpoint token is kept (other judges depend on it).
        add(_ENDPOINT in ans, f"EN {q!r}: endpoint token dropped in 「{first}」")

    for q in _JA_QS:
        ans = _no_evidence_answer(q)
        # 5: the Japanese reply stays a no-evidence reply.
        add(_JA_MARKER in ans, f"JA {q!r}: opening marker missing")
        # 6: ...and keeps routing ingestion through the administrator.
        add("管理者" in ans, f"JA {q!r}: no longer asks the administrator")

    total = len(_EN_QS) * 4 + len(_JA_QS) * 2
    return NoEvidenceEnglishAdminFramedResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "NoEvidenceEnglishAdminFramedResult",
    "evaluate_no_evidence_english_admin_framed",
]
