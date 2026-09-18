"""Does a PGP private key block get caught the way every other PEM key does?

C-1961. The ``private_key_block`` secret pattern matched
``-----BEGIN[ WORD]? PRIVATE KEY-----`` but required ``-----`` immediately
after ``PRIVATE KEY``. A PGP private key announces itself as
``-----BEGIN PGP PRIVATE KEY BLOCK-----`` - the extra ``BLOCK`` word meant the
pattern never matched, so a PGP private key passed **both** trust boundaries:
the ingestion gate returned ALLOW (the key would be indexed) and the output
guard returned it unblocked (the key would reach the operator and the logs).
RSA/OPENSSH/EC keys, which end at ``PRIVATE KEY-----``, were caught. The fix
adds an optional `` BLOCK`` to both ends of the pattern, so the one shared
``SecretDetector`` closes the hole on both boundaries at once.

The checks drive the real ``OutputGuard.scan`` (the output boundary) and the
real ``SecurityGate.inspect`` with ``source="github"`` (the ingestion
boundary) over PGP, RSA, OPENSSH and EC key blocks, plus clean-text negative
controls so the tightening cannot silently start blocking ordinary answers.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.security.decisions import Decision
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate
from sidra_ai.security.output_guard import OutputGuard


@dataclass(frozen=True)
class OutputGuardPgpResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _body() -> str:
    # A deterministic-enough base64 body; content is irrelevant, the header
    # wording is what the pattern keys on.
    return "\n".join(
        base64.b64encode((f"sidra-c1961-line-{i}").encode() + os.urandom(24)).decode()
        for i in range(16)
    )


def _key(label: str) -> str:
    return f"-----BEGIN {label}-----\n{_body()}\n-----END {label}-----"


#: The forms that end in "PRIVATE KEY BLOCK" - the ones the old pattern missed.
_BLOCK_FORMS = ("PGP PRIVATE KEY BLOCK",)
#: The forms that end in "PRIVATE KEY" - already caught, must stay caught.
_PLAIN_FORMS = (
    "RSA PRIVATE KEY",
    "OPENSSH PRIVATE KEY",
    "EC PRIVATE KEY",
    "PRIVATE KEY",
    "DSA PRIVATE KEY",
)
#: Ordinary answers that must never be blocked by this tightening.
_CLEAN = (
    "デプロイはmainへのpushで自動的に走ります。所要時間は5分です。",
    "Answering from indexed repository DATA. Deploy runs on push to main.",
    "秘密鍵の作り方は README に書いてある（このテキスト自体は鍵ではない）。",
    "The private key lives in a vault; ask the administrator for access.",
)


def _gate() -> SecurityGate:
    # Through the shared helper, never tempfile directly: scratch_dir registers
    # the directory for removal at interpreter exit, the contract C-1770 pins
    # and evals_clean_up_their_scratch enforces by AST.
    tmp = scratch_dir()
    return SecurityGate(
        GatePolicy(),
        allowed_repositories=("r/r",),
        quarantine_store=QuarantineStore(os.path.join(tmp, "q.jsonl")),
    )


def evaluate_output_guard_blocks_pgp_private_key() -> OutputGuardPgpResult:
    guard = OutputGuard()
    gate = _gate()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # (A) the fix: PGP "PRIVATE KEY BLOCK" is caught on BOTH boundaries.
    for form in _BLOCK_FORMS:
        text = _key(form)
        r = guard.scan(text)
        add(r.blocked, f"A output: {form} not blocked")
        add(
            "private_key_block" in (r.finding_labels or ()),
            f"A output: {form} label missing ({r.finding_labels})",
        )
        g = gate.inspect(text, source="github", repository="r/r")
        add(
            g.decision is not Decision.ALLOW,
            f"A ingest: {form} decision={g.decision.name} (want not ALLOW)",
        )
        add(
            "private_key_block" in {f.detector for f in (g.findings or ())},
            f"A ingest: {form} finding missing",
        )

    # (B) controls: the plain "PRIVATE KEY" forms stay caught (no regression).
    for form in _PLAIN_FORMS:
        text = _key(form)
        add(guard.scan(text).blocked, f"B output: {form} not blocked")
        add(
            gate.inspect(text, source="github", repository="r/r").decision
            is not Decision.ALLOW,
            f"B ingest: {form} became ALLOW",
        )

    # (C) negative controls: ordinary answers are not blocked by the tightening.
    for text in _CLEAN:
        r = guard.scan(text)
        add(not r.blocked, f"C output: clean text blocked ({text[:24]!r})")

    total = checks + len(failures)
    return OutputGuardPgpResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )
