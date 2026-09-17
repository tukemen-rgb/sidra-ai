"""Does an English subject-less follow-up ground on the topic under discussion?

C-1912. The Japanese elaboration follow-up 「もっと詳しく」 carries the previous
question's subject (C-1453/C-1810/C-1828), so "How does authentication work?"
followed by 「もっと詳しく」 stays on authentication. But its English twin,
"Tell me more", did not: ``_own_content_subject`` read "tell", "me" and "more"
as topic terms, so the carry in ``SidraService.chat`` was skipped and the
follow-up searched literally - "No indexed evidence matched this question." The
Japanese side had ``_JP_ELABORATIONS``; the English side had only the
interrogatives (why/how/what), not the elaboration fillers, so an English
speaker's most natural follow-up fell through.

The fix adds an English elaboration set (the twin of ``_JP_ELABORATIONS``) so a
pure elaboration phrase names no subject of its own and grounds on the topic
under discussion. A follow-up that names a real subject ("tell me about
billing") keeps it and is not carried off; single-turn retrieval is unchanged.
Measured through the real ``SidraService.chat`` with the echo backend, reading
which document each turn cites.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sidra_ai.evals.scratch import scratch_dir

_AUTH = "docs/auth_en.md"
_DEPLOY = "docs/deploy_en.md"
_BILLING = "docs/billing_en.md"


def _service():
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

    allowed = ("tukemen-rgb/site",)
    tmp = Path(scratch_dir())
    settings = Settings(allowed_repositories=allowed, data_dir=str(tmp / "sidra"))
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=allowed,
        quarantine_store=QuarantineStore(tmp / "q.jsonl"),
    )
    store = DocumentStore(gate)

    def doc(content: str, path: str) -> Document:
        return Document(
            content=content,
            provenance=Provenance(
                source="github", repository="tukemen-rgb/site", path=path,
                commit_sha="c" * 40, timestamp=datetime.now(timezone.utc),
                source_type=SourceType.DOCS, trust_level=TrustLevel.INTERNAL_REPO,
                license="MIT",
            ),
        )

    store.add(doc(
        "Authentication uses OAuth2 for login. Access tokens expire after 3600 "
        "seconds. Refresh tokens are stored in Redis and last thirty days.", _AUTH))
    store.add(doc(
        "Deployment uses GitHub Actions. Images are pushed to the registry.", _DEPLOY))
    store.add(doc(
        "Billing runs on the first of each month. Invoices are emailed to "
        "customers.", _BILLING))
    return SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)


def _paths(result) -> list[str]:
    return [c["path"] for c in (result.get("citations") or [])]


#: Pure elaboration follow-ups: each must ground on the topic under discussion.
_ELABORATIONS = (
    "Tell me more",
    "tell me more",
    "more",
    "more detail",
    "more details",
    "explain more",
    "elaborate",
    "tell me more about that",
    "can you elaborate",
)


@dataclass(frozen=True)
class EnglishFollowupResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_chat_english_followup_carries_the_subject() -> EnglishFollowupResult:
    svc = _service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    q1 = "How does authentication work?"
    r1 = svc.chat(q1)
    hist = [(q1, r1["answer"])]
    add(_paths(r1)[:1] == [_AUTH], f"Q1 did not cite auth: {_paths(r1)}")

    # (A) each English elaboration follow-up grounds on authentication.
    for fu in _ELABORATIONS:
        paths = _paths(svc.chat(fu, history=hist))
        add(paths[:1] == [_AUTH],
            f"elaboration {fu!r} did not ground on auth (first={paths[:1]}, all={paths})")

    # (B) a follow-up that names a REAL subject is not carried off it: "tell me
    # about billing" keeps billing though tell/me/about are elaboration fillers.
    bill = _paths(svc.chat("tell me about billing", history=hist))
    add(bill[:1] == [_BILLING],
        f"a real subject beside elaboration fillers was swallowed: {bill}")

    # (B2) a bare single-word new subject must not be swallowed as elaboration:
    # "Billing?" alone names billing and grounds there, not on the carried auth
    # topic. This fails loudly if a real topic word leaks into _EN_ELABORATIONS.
    solo = _paths(svc.chat("Billing?", history=hist))
    add(solo[:1] == [_BILLING] and _AUTH not in solo,
        f"a bare new subject was swallowed as elaboration and carried: {solo}")

    # (C) a follow-up naming a NEW subject grounds there, not on the old topic.
    # Singular "deployment" so the check is about the carry, not the separate
    # plural-retrieval gap (C-1911 folds plurals only in the answer opening).
    dep = _paths(svc.chat("How does deployment work?", history=hist))
    add(dep[:1] == [_DEPLOY],
        f"new-subject follow-up was carried off its subject: {dep}")
    add(_AUTH not in dep, f"new-subject follow-up over-carried the old topic: {dep}")

    # (D) single-turn retrieval with a real subject is unchanged.
    add(_paths(svc.chat("authentication"))[:1] == [_AUTH],
        "single-turn subject query changed")

    total = 1 + len(_ELABORATIONS) + 5
    return EnglishFollowupResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "EnglishFollowupResult",
    "evaluate_chat_english_followup_carries_the_subject",
    "_ELABORATIONS",
]
