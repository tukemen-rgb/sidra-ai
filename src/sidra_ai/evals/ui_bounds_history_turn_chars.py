"""Does the conversation UI bound a history turn's length, like the server does?

C-1684. The entry page mirrors the server's ``MAX_HISTORY_TURNS`` as ``MAX_TURNS``
and caps the number of replayed turns client-side, but it has no mirror for
``MAX_HISTORY_TURN_CHARS`` (8000). A prior answer longer than that was pushed
into ``turns`` and replayed as ``history`` on the next question, which the server
rejects with 422 - so the next (short) question failed with "shorten your
input", pointing the reader at the wrong thing. The page now records a turn into
history only when its question and answer both fit the limit.

The checks read the page source (a turn is recorded only within the char limit,
mirroring the server constant) and drive the real endpoint to pin the boundary.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path


def _client():
    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import SecurityGate

    gate = SecurityGate()
    store = DocumentStore(gate)
    settings = Settings(data_dir=tempfile.mkdtemp())
    service = SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)
    return TestClient(create_app(service=service, settings=settings))


@dataclass(frozen=True)
class UiHistoryCharsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_bounds_history_turn_chars() -> UiHistoryCharsResult:
    import re

    from sidra_ai.api.schemas import MAX_HISTORY_TURN_CHARS
    from sidra_ai.api.ui import ASK_PAGE

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (1) the page declares a per-turn char limit ---
    m = re.search(r"MAX_TURN_CHARS\s*=\s*(\d+)", ASK_PAGE)
    add(m is not None, "1: ASK_PAGE does not declare MAX_TURN_CHARS")

    # --- (2) recording a turn into history is gated on length for BOTH the
    #         question and the answer (two MAX_TURN_CHARS comparisons) ---
    start = ASK_PAGE.find("turns.push(")
    window = ASK_PAGE[max(0, start - 400): start] if start != -1 else ""
    add(window.count("MAX_TURN_CHARS") >= 2 and "answer.length" in window,
        f"2: turns.push not gated on both fields (count={window.count('MAX_TURN_CHARS')})")

    # --- (3) the constant mirrors the server's limit ---
    add(m is not None and int(m.group(1)) == MAX_HISTORY_TURN_CHARS,
        f"3: MAX_TURN_CHARS != server MAX_HISTORY_TURN_CHARS ({MAX_HISTORY_TURN_CHARS})")

    # --- (4) the server rejects an over-long history turn (the boundary) ---
    client = _client()
    big = {"question": "q", "answer": "x" * (MAX_HISTORY_TURN_CHARS + 1000)}
    r_big = client.post("/v1/chat", json={"message": "y", "history": [big]})
    add(r_big.status_code == 422, f"4: over-long history turn not 422 ({r_big.status_code})")

    # --- (5) an in-limit history turn is accepted ---
    ok = {"question": "本社の定休日は？", "answer": "月曜が定休です。"}
    r_ok = client.post("/v1/chat", json={"message": "それはなぜ？", "history": [ok]})
    add(r_ok.status_code == 200, f"5: in-limit history turn not accepted ({r_ok.status_code})")

    # --- (6) the turn-count cap is still present (no regression) ---
    add("MAX_TURNS" in ASK_PAGE and "slice(-MAX_TURNS)" in ASK_PAGE,
        "6: the turn-count cap regressed")

    total = 6
    return UiHistoryCharsResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["UiHistoryCharsResult", "evaluate_ui_bounds_history_turn_chars"]
