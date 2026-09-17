"""Does the CLI's how_to_make reply read as an invitation, not an outage?

C-1933, the text-side sibling of C-1931. A ``how_to_make`` reply (C-1875) is
conversational: the service composes a useful, language-branched body - "you
can make a report right here; send what you want, with a subject". C-1931 gave
that reply exit code 4 (conversational, not the outage 1) by adding it to
``_CONVERSATIONAL_REFUSALS``. But the human-readable text was left behind:
``ask_cli``'s ``messages`` dict - which supplies the terminal line for every
refusal code - had no ``how_to_make`` entry, so it fell to the decision-based
fallback and printed 「回答を出せなかった。少し時間をおいて、もう一度試す。」,
the *outage* "wait and retry" line, for a reply that never changes on retry.

Adding ``how_to_make`` to ``how do I make one`` was three downstream places -
the web UI's refusalMsg map (C-1875), the CLI exit-code set (C-1931), and the
CLI message dict (this). The first two were filled; this fills the third.

This eval drives the real service to produce the payload (so a code rename
cannot pass it), renders it through ``ask_cli.render``, and asserts the line
invites creation and is not the outage line - while keeping the safety (3),
outage (1) and unknown-code fallback controls so the fix cannot widen.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.ask_cli import render
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: "how do I make one" questions the service answers with a how_to_make reply.
HOW_TO_QUESTIONS: tuple[str, ...] = (
    "レポートの作り方を教えて",
    "ゲームの作り方は",
    "how do I make a report",
)

#: The signature of the outage fallback - "wait a while and try again" - which
#: must never be what a how_to_make reply prints.
_OUTAGE_LINE = "少し時間をおいて"
#: The invitation cue the fixed line carries: "you can make it right here".
_INVITE_CUE = "この場で作れる"
#: A concrete example of how to ask, so the reader has a next step.
_EXAMPLE_CUE = "作って"


@dataclass(frozen=True)
class CliHowToMakeMessageResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service() -> SidraService:
    root = Path(scratch_dir("sidra-c1933-"))
    return SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )


def _render_capture(payload: dict) -> tuple[str, int]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = render(dict(payload))
    return buf.getvalue(), code


def evaluate_cli_how_to_make_message_invites_creation() -> CliHowToMakeMessageResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    service = _service()

    # (A) every how_to_make reply renders as an invitation, exit 4, never the
    #     outage "wait and retry" line - for JP and EN phrasings alike (the CLI
    #     line is keyed on the code, so it appears whatever language asked).
    for q in HOW_TO_QUESTIONS:
        payload = service.chat(q)
        add(payload.get("refusal") == "how_to_make",
            f"A: {q!r} did not yield a how_to_make reply: {payload.get('refusal')!r}")
        text, code = _render_capture(payload)
        add(_INVITE_CUE in text,
            f"A: {q!r} CLI text has no invitation cue: 「{text.strip()[:160]}」")
        add(_OUTAGE_LINE not in text,
            f"A: {q!r} CLI text still prints the outage line: 「{text.strip()[:160]}」")
        add(code == 4, f"A: {q!r} exit {code} (want 4, conversational)")

    # (B) the reply names a concrete way to ask, not just "you can make things".
    text, _ = _render_capture(service.chat("レポートの作り方を教えて"))
    add(_EXAMPLE_CUE in text, f"B: no example of how to ask: 「{text.strip()[:160]}」")

    # (C) controls - the fix must not widen. A safety block still reads as a
    #     refusal (exit 3), a genuine outage still says wait (exit 1), and an
    #     unknown code still reaches the decision-based fallback unchanged.
    gate = {"refused": True, "refusal": "gate", "answer": "",
            "security": {"decision": "quarantine"}, "citations": []}
    text, code = _render_capture(gate)
    add(code == 3, f"C gate: exit {code} (want 3)")
    add("回答を拒否した。" in text, "C gate: missing the refusal preface")
    add("安全性チェック" in text, "C gate: missing the safety line")

    outage = {"refused": True, "refusal": "model_unavailable", "answer": "",
              "security": {"decision": "allow"}, "citations": []}
    text, code = _render_capture(outage)
    add(code == 1, f"C outage: exit {code} (want 1)")
    add("ローカルモデルに接続できていない" in text, "C outage: missing the outage line")

    unknown = {"refused": True, "refusal": "not_a_real_code", "answer": "",
               "security": {"decision": "allow"}, "citations": []}
    text, code = _render_capture(unknown)
    add(code == 1, f"C unknown: exit {code} (want 1)")
    add(_OUTAGE_LINE in text, "C unknown: the decision-based fallback was lost")

    total = len(HOW_TO_QUESTIONS) * 4 + 1 + 7
    return CliHowToMakeMessageResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "CliHowToMakeMessageResult",
    "evaluate_cli_how_to_make_message_invites_creation",
]
