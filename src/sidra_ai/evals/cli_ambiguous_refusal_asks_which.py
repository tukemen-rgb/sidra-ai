"""Does the sidra-ask CLI give ambiguous queries a real next step, like the web UI?

C-1713. An ambiguous query - a bare noun like 「レースゲーム」 that names a thing
without asking for anything - makes the service reply ``refusal: "ambiguous"`` and
ask which was meant, build one or find one (C-1670). The web UI's refusal map got a
tailored message for that code; the CLI's ``render`` map (gate/history/
model_unavailable/output_guard/empty) never did, so an ambiguous refusal fell to
the generic 「回答を出せなかった。少し時間をおいて、もう一度試す。」 - advice that
repeats the same ambiguity, and the same client asymmetry C-1675/1689/1691/1705
kept closing. ``render`` now names both choices for an ambiguous refusal.

The checks drive ``render`` with an ambiguous payload and the real ``/v1/chat``:
the ambiguous output names build *and* find with a build example and drops the
generic wait-and-retry line, while a gate refusal keeps its own message and an
unknown refusal code still falls back gracefully.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone

_WAIT_RETRY = "少し時間をおいて"


def _render(payload: dict) -> str:
    from sidra_ai.api.ask_cli import render

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        render(payload)
    return buf.getvalue()


def _refusal_payload(refusal: str, *, answer: str = "", decision: str = "allow",
                     model: bool = False) -> dict:
    payload: dict = {
        "answer": answer,
        "refused": True,
        "refusal": refusal,
        "security": {"decision": decision},
        "citations": [],
    }
    if model:
        payload["model"] = {"backend": "echo", "name": "x"}
    return payload


def _chat_ambiguous_render() -> str:
    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app
    from sidra_ai.api.ask_cli import render
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
    store.add(Document(content="本社の定休日は毎週月曜日です。", provenance=prov))
    settings = Settings(data_dir=tempfile.mkdtemp())
    service = SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)
    client = TestClient(create_app(service=service, settings=settings))
    payload = client.post("/v1/chat", json={"message": "レースゲーム"}).json()
    assert payload.get("refusal") == "ambiguous", payload.get("refusal")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        render(payload)
    return buf.getvalue()


@dataclass(frozen=True)
class CliAmbiguousResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_ambiguous_refusal_asks_which() -> CliAmbiguousResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    amb = _render(_refusal_payload("ambiguous"))

    # --- (A) the ambiguous output names both choices: build and find ---
    add("作る" in amb and "探す" in amb, f"A: ambiguous output names no build/find choice: {amb!r}")

    # --- (B) it gives a build example (「…を作って」のように) ---
    add("作って" in amb, f"B: ambiguous output gives no build example: {amb!r}")

    # --- (C) the generic wait-and-retry advice is gone (it repeats the ambiguity) ---
    add(_WAIT_RETRY not in amb, f"C: ambiguous output still says wait-and-retry: {amb!r}")

    # --- (D) a gate refusal keeps its own message (no regression) ---
    gate = _render(_refusal_payload("gate", decision="block"))
    add("安全性チェック" in gate, f"D: gate refusal lost its message: {gate!r}")

    # --- (E) an unknown refusal code still falls back gracefully ---
    unknown = _render(_refusal_payload("something_new_and_unmapped"))
    add(_WAIT_RETRY in unknown,
        f"E: an unknown refusal code lost its graceful fallback: {unknown!r}")

    # --- (F) end-to-end: a real /v1/chat ambiguous answer renders with guidance ---
    live = _chat_ambiguous_render()
    add("作る" in live and "探す" in live and _WAIT_RETRY not in live,
        f"F: the real ambiguous refusal did not render a next step: {live!r}")

    total = 6
    return CliAmbiguousResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["CliAmbiguousResult", "evaluate_cli_ambiguous_refusal_asks_which"]
