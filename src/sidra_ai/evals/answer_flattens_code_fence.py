"""Does answer/evidence flattening strip a code fence cleanly?

C-1695. ``plain_text`` flattens Markdown decoration, but had no case for a fenced
code block. ``_MD_CODE`` matches only an inline single-backtick span, so a triple
backtick fence lost one backtick per side and left ``\`\``` artifacts (```` ```bash
… ``` ```` became ``\`\`bash … \`\```), and a ``~~~`` fence survived whole. That
flattening feeds the chat answer's facts, the echo backend and generated
documents, so any indexed README with a code block put stray fence marks into the
answer a reader sees. ``plain_text`` now removes fence-delimiter lines while
keeping the code text as prose.

The checks drive ``plain_text`` directly and the real ``/v1/chat``: a fenced block
leaves no backtick or ``~~~`` artifact, the code text survives, and inline code
and plain prose are unchanged.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone


def _chat_answer(message: str, doc_content: str) -> str:
    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, SecurityGate

    gate = SecurityGate(GatePolicy(), allowed_repositories=("acme/h",))
    store = DocumentStore(gate)
    prov = Provenance(
        source="github", repository="acme/h", path="a.md", commit_sha="abc1234",
        timestamp=datetime.now(timezone.utc), source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO, license="proprietary",
    )
    store.add(Document(content=doc_content, provenance=prov))
    settings = Settings(data_dir=tempfile.mkdtemp())
    service = SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)
    client = TestClient(create_app(service=service, settings=settings))
    return client.post("/v1/chat", json={"message": message}).json().get("answer", "")


@dataclass(frozen=True)
class CodeFenceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_answer_flattens_code_fence() -> CodeFenceResult:
    from sidra_ai.creation.evidence import plain_text

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    backtick = (
        "# インストール手順\n\n次を実行:\n\n```bash\nnpm install\nnpm run build\n```\n\n完了。"
    )
    flat = plain_text(backtick)

    # --- (A) a backtick fence leaves no backtick artifact ---
    add("`" not in flat, f"A: a backtick artifact survived: {flat!r}")

    # --- (B) the code text survives (no content dropped) ---
    add("npm install" in flat and "npm run build" in flat,
        f"B: the code text was lost: {flat!r}")

    # --- (C) inline code still keeps its content and drops the backticks ---
    inline = plain_text("設定は `config.json` にある。")
    add("config.json" in inline and "`" not in inline,
        f"C: inline code regressed: {inline!r}")

    # --- (D) a ~~~ fence is removed too ---
    tilde = plain_text("手順:\n\n~~~yaml\nkey: value\n~~~\n\n以上。")
    add("~~~" not in tilde and "key: value" in tilde,
        f"D: a ~~~ fence survived: {tilde!r}")

    # --- (E) a real /v1/chat answer over a fenced doc shows no fence artifact ---
    answer = _chat_answer("インストール手順を教えて", backtick)
    add("``" not in answer and "npm install" in answer,
        f"E: the chat answer carried a fence artifact: {answer[:160]!r}")

    # --- (F) plain prose is unchanged (no over-stripping) ---
    prose = "ただの文章です。句点で終わる。"
    add(plain_text(prose) == prose, "F: plain prose was altered")

    total = 6
    return CodeFenceResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["CodeFenceResult", "evaluate_answer_flattens_code_fence"]
