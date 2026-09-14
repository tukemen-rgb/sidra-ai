"""A revision that names no target asks which, not "no evidence".

C-1797. ``detect_revision_intent`` requires a back-reference (それ/さっきの) so it
never edits an artifact nobody pointed at. But a bare 「もっと難しくして」 -
the most natural way to ask right after making something - has no back-reference,
so it fell through to retrieval and got the no-evidence abstention that names
「POST /v1/github/analyze」. A change instruction with a recognised adjustment but
no target is now answered like empty/ambiguous/unnamed/greeting: a friendly
``refusal == "revision_target"`` that asks which artifact and shows how to point
at it. A proper revision (「さっきのを難しくして」) and a real question are
untouched.

The checks drive the real ``SidraService.chat`` over the echo backend.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.evals.scratch import scratch_dir

_NO_EVIDENCE = "現時点では十分な根拠がありません"
_ENDPOINT = "/v1/github/analyze"
_CODE = "revision_target"


@dataclass(frozen=True)
class ReferentlessRevisionResult:
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

    tmp = Path(scratch_dir(prefix="referentless-rev-"))
    repo = "tukemen-rgb/sidra-ai"
    settings = Settings(allowed_repositories=(repo,), data_dir=str(tmp / "sidra"))
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=(repo,),
        quarantine_store=QuarantineStore(tmp / "quarantine.jsonl"),
    )
    return SidraService(settings, store=DocumentStore(gate), gate=gate)


def evaluate_chat_referentless_revision_asks_which() -> ReferentlessRevisionResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    svc = _service()

    harder = svc.chat("もっと難しくして")
    rename = svc.chat("タイトルを「夜のレース」にして")
    theme = svc.chat("紙のテーマにして")
    question = svc.chat("火星の天気を教えて")
    referenced = svc.chat("さっきのゲームを難しくして")

    # --- (A) a referent-less "harder" asks which artifact ----------------
    add(harder.get("refusal") == _CODE,
        f"A: 「もっと難しくして」 was not asked-back (refusal={harder.get('refusal')!r})")
    # --- (B) it is not the no-evidence abstention ------------------------
    add(_NO_EVIDENCE not in harder.get("answer", "") and _ENDPOINT not in harder.get("answer", ""),
        "B: the referent-less revision got the no-evidence abstention (names the endpoint)")
    # --- (C) a referent-less rename asks which too -----------------------
    add(rename.get("refusal") == _CODE,
        f"C: 「タイトルを…にして」 was not asked-back (refusal={rename.get('refusal')!r})")
    # --- (D) a referent-less theme change asks which too -----------------
    add(theme.get("refusal") == _CODE,
        f"D: 「紙のテーマにして」 was not asked-back (refusal={theme.get('refusal')!r})")
    # --- (E) a real question is not mistaken for a revision -------------
    add(question.get("refusal") != _CODE,
        "E: a real question was wrongly asked-back as a revision")
    # --- (F) a properly referenced revision is not asked-back -----------
    add(referenced.get("refusal") != _CODE,
        "F: 「さっきのゲームを難しくして」 was asked-back instead of revised")

    total = 6
    return ReferentlessRevisionResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ReferentlessRevisionResult",
    "evaluate_chat_referentless_revision_asks_which",
]
