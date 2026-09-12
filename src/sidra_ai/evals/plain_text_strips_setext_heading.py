"""Does answer/evidence flattening strip a setext heading underline?

C-1709. ``plain_text`` flattens Markdown decoration, and C-1695 taught it about
fenced code blocks, but a *setext* H1 heading was still missed. A setext H1 is a
title line followed by a line of ``=`` characters (``タイトル\n===``); the
underline row is pure syntax, no content. ATX headings (``# タイトル``) were
stripped by ``_MD_HEADING`` and a setext H2's ``---`` underline happened to be
caught by ``_MD_TABLE_SEP`` (which removes a ``-{2,}`` line), but nothing removed
a ``=`` line, so ``タイトル\n===\n\n本文`` flattened to 「タイトル === 本文」 - a
raw ``===`` artifact in an answer or generated document, the same class of leak
as the code-fence bug. ``plain_text`` now removes a setext ``=`` underline line
while keeping the heading text and the body.

The checks drive ``plain_text`` directly and the real ``/v1/chat``: a setext
underline leaves no ``=`` artifact, the heading and body text survive, a longer
underline is removed too, a mid-line ``=`` in prose is untouched (no
over-stripping), and a real answer over such a document carries no artifact.
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
class SetextResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_plain_text_strips_setext_heading() -> SetextResult:
    from sidra_ai.creation.evidence import plain_text

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    doc = "インストール手順\n===\n\nまず npm install を実行する。\n"
    flat = plain_text(doc)

    # --- (A) a setext H1 underline leaves no bare = artifact ---
    add("=" not in flat, f"A: a setext underline artifact survived: {flat!r}")

    # --- (B) the heading text and body both survive (no content dropped) ---
    add("インストール手順" in flat and "npm install を実行する" in flat,
        f"B: heading or body text was lost: {flat!r}")

    # --- (C) a longer underline is removed too ---
    long_rule = plain_text("概要\n========\n\n続く段落。")
    add("=" not in long_rule and "概要" in long_rule and "続く段落" in long_rule,
        f"C: a long setext underline survived: {long_rule!r}")

    # --- (D) a mid-line = in prose is untouched (no over-stripping) ---
    inline = plain_text("設定は key=value 形式で書く。")
    add("key=value" in inline, f"D: a mid-line = was over-stripped: {inline!r}")

    # --- (E) a real /v1/chat answer over a setext-heading doc has no artifact ---
    answer = _chat_answer("インストール手順を教えて", doc)
    add("=" not in answer and "npm install" in answer,
        f"E: the chat answer carried a setext artifact: {answer[:160]!r}")

    # --- (F) plain prose is unchanged (no over-stripping) ---
    prose = "ただの文章です。句点で終わる。"
    add(plain_text(prose) == prose, "F: plain prose was altered")

    total = 6
    return SetextResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["SetextResult", "evaluate_plain_text_strips_setext_heading"]
