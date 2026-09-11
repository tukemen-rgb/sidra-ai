"""Does ``sidra-ask`` stop advertising a zero external-API cost on every answer?

C-1668. The answer footer reads ``(<backend>, 外部 API 費用 $<cost>)``. v0.1
forbids external APIs - ``models/usage.py`` raises on a paid call and
``totals()`` always sums to ``0.0`` (never ``None``) - so the ``cost is not
None`` guard never suppressed the clause, and every local answer ended with
``(ollama, 外部 API 費用 $0.0)``: an external-API-cost line on a product whose
whole promise is that it never calls one. The clause now shows only when a cost
was actually incurred.

The checks drive ``render`` on three payloads shaped exactly like the chat
endpoint's ``model`` block: a normal local answer (cost 0.0 - the clause must be
gone, but the backend note stays), a hypothetical paid answer (cost 0.02 - the
clause must still appear so a real cost is never hidden), and a missing cost.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass

_COST_PHRASE = "外部 API 費用"


def _render(model: dict) -> tuple[int, str]:
    """Render a normal (non-refused) answer carrying the given model block."""
    from sidra_ai.api import ask_cli

    payload = {
        "answer": "月曜が定休です。[S1]",
        "refused": False,
        "citations": [
            {
                "label": "S1",
                "citation": "acme/handbook@abc1234:hours.md",
                "trust_level": "internal_repo",
            }
        ],
        "model": model,
        "creation": {"intent": "qa"},
    }
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = ask_cli.render(payload)
    return code, out.getvalue()


@dataclass(frozen=True)
class AskCostResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ask_answer_hides_zero_external_cost() -> AskCostResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) normal local answer, cost 0.0: no external-cost line, backend kept ---
    code, out = _render({"backend": "ollama", "name": "llama3.1:8b",
                         "external_api_cost_usd": 0.0})
    add(_COST_PHRASE not in out,
        f"A: a local answer still advertised an external-API cost: {out!r}")
    add("(ollama" in out,
        f"A: the backend note was lost with the cost clause: {out!r}")
    add(code == 0, f"A: exit {code}, expected 0")

    # --- (B) a real paid cost must still be shown ---
    _, out = _render({"backend": "anthropic", "external_api_cost_usd": 0.02})
    add(f"{_COST_PHRASE} $0.02" in out,
        f"B: a real external cost was hidden: {out!r}")
    add("(anthropic" in out, f"B: the backend note was lost: {out!r}")

    # --- (C) missing cost: no cost line, backend kept ---
    _, out = _render({"backend": "ollama", "external_api_cost_usd": None})
    add(_COST_PHRASE not in out and "(ollama" in out,
        f"C: cost None mishandled: {out!r}")

    total = 6
    return AskCostResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["AskCostResult", "evaluate_ask_answer_hides_zero_external_cost"]
