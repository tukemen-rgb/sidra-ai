"""Does an empty /v1/chat message reach the C-1515 ask-back, like the service does?

C-1536 (辛口コメンテーター 第11回). ``SidraService.chat("")`` answers an empty
message with a friendly ask-back - 「質問が空のようです。何について調べますか」
(C-1515) - and so does a whitespace, newline or full-width-space message over
HTTP (they pass the schema and reach the service). But an *empty string* was
rejected at the HTTP boundary by ``ChatRequest.message``'s ``min_length=1`` with a
bare 422 「request validation failed」, so the one input the ask-back was written
for never reached it. Humans do not hit this (the browser page stops empty with
``required``); a direct API caller does. Dropping ``min_length`` unifies the empty
case in the service layer while the ``max_length`` cap stays (an over-long post is
still a correct 422).

The checks drive the real ``/v1/chat`` (TestClient) and the service: empty now
reaches the ask-back over HTTP, both paths deliver it (the item's metric 1→2), the
length cap still rejects an over-long message, whitespace still asks back, and an
ordinary question is still answered.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.evals.scratch import scratch_dir

#: Common to the service ask-back and enough to tell it from a gate/other reply.
_ASK_BACK = "質問が空"


def _client_and_service():
    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, SecurityGate

    settings = Settings(data_dir=scratch_dir("c1536-"))
    gate = SecurityGate(GatePolicy(), allowed_repositories=("acme/app",))
    service = SidraService(settings, model=EchoModelAdapter(),
                           store=DocumentStore(gate), gate=gate)
    return TestClient(create_app(service, settings)), service


@dataclass(frozen=True)
class EmptyAskBackResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_empty_message_reaches_the_ask_back() -> EmptyAskBackResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    client, service = _client_and_service()

    # --- (A) the service layer answers empty with the ask-back (C-1515) ------
    svc_empty = service.chat("")
    svc_ok = svc_empty.get("refusal") == "empty" and _ASK_BACK in (svc_empty.get("answer") or "")
    add(svc_ok, f"A: the service no longer asks back on empty: {svc_empty.get('answer')!r}")

    # --- (B) HTTP empty is accepted (200), not rejected at the schema (422) --
    resp = client.post("/v1/chat", json={"message": ""})
    add(resp.status_code == 200, f"B: HTTP empty was {resp.status_code}, not 200")

    # --- (C) HTTP empty reaches the ask-back ---------------------------------
    body = resp.json() if resp.status_code == 200 else {}
    http_ok = body.get("refusal") == "empty" and _ASK_BACK in (body.get("answer") or "")
    add(http_ok, f"C: HTTP empty did not reach the ask-back: {body.get('answer')!r}")

    # --- (D) the item's metric: both paths deliver the ask-back (1 -> 2) -----
    paths = int(svc_ok) + int(http_ok)
    add(paths == 2, f"D: only {paths}/2 paths deliver the empty ask-back")

    # --- (E) the length cap still rejects an over-long message (regression) --
    over = client.post("/v1/chat", json={"message": "あ" * 32_001})
    add(over.status_code == 422, f"E: an over-long message was {over.status_code}, not 422")

    # --- (F) whitespace still asks back (unchanged) --------------------------
    ws = client.post("/v1/chat", json={"message": "   "})
    add(ws.status_code == 200 and ws.json().get("refusal") == "empty",
        f"F: whitespace regressed: {ws.status_code}")

    # --- (G) an ordinary question is still answered, not treated as empty ----
    q = client.post("/v1/chat", json={"message": "SIDRAとは何ですか"})
    add(q.status_code == 200 and q.json().get("refusal") != "empty",
        f"G: an ordinary question was mishandled: {q.status_code}/{q.json().get('refusal')}")

    total = 7
    return EmptyAskBackResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["EmptyAskBackResult", "evaluate_empty_message_reaches_the_ask_back"]
