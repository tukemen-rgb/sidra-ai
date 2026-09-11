"""Does ``sidra-ask`` give per-reason refusal guidance, like the web UI?

C-1675. The service tags every refusal with a fixed ``refusal`` code
(``gate``/``history``/``model_unavailable``/``output_guard``/``empty``). The web
UI switched to those codes (C-1157) so a stopped model, a blocked history and a
withheld answer each get a next step that actually helps. ``ask_cli.render``
still keyed only on ``security.decision`` (two branches), so every non-gate
refusal printed "回答を出せなかった。少し時間をおいて、もう一度試す" - "wait and
try again", which fixes none of them. render() now keys on ``refusal`` too.

The checks drive ``render`` with each refusal shape the service emits and assert
the message names the real next step (and drops the misleading "wait" advice),
while the gate message and the refusal exit codes are unchanged.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass

_WAIT = "少し時間をおいて"


def _render(payload) -> tuple[int, str]:
    from sidra_ai.api import ask_cli

    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = ask_cli.render(payload)
    return code, out.getvalue()


def _refused(refusal, decision="allow", model=None):
    payload = {
        "refused": True,
        "refusal": refusal,
        "reason": "english audit text",
        "citations": [],
        "security": {"decision": decision},
    }
    if model is not None:
        payload["model"] = model
    return payload


@dataclass(frozen=True)
class RefusalMsgResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ask_refusal_message_matches_reason() -> RefusalMsgResult:
    from sidra_ai.api.ask_cli import _refusal_exit_code

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # (A) model_unavailable: name the model / echo backend, not "wait" ---
    p = _refused("model_unavailable")
    code, out = _render(p)
    add(("モデル" in out or "echo" in out) and _WAIT not in out,
        f"A: model_unavailable guidance did not name the model or still said wait: {out!r}")
    add(code == _refusal_exit_code(p), f"A: exit {code} != {_refusal_exit_code(p)}")

    # (B) output_guard (answer generated then withheld): "same question, same result"
    p = _refused("output_guard", model={"backend": "ollama"})
    code, out = _render(p)
    add("同じ質問" in out and _WAIT not in out,
        f"B: output_guard guidance was generic/wait: {out!r}")

    # (C) history: point at the conversation, not "wait"
    p = _refused("history")
    _, out = _render(p)
    add("会話" in out and _WAIT not in out,
        f"C: history guidance did not name the conversation: {out!r}")

    # (D) gate: still asks for a rephrase (unchanged)
    p = _refused("gate", decision="quarantine")
    code, out = _render(p)
    add("言い換え" in out, f"D: gate guidance lost the rephrase advice: {out!r}")
    add(code == _refusal_exit_code(p) == 3, f"D: gate exit {code} != 3")

    total = 6
    return RefusalMsgResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["RefusalMsgResult", "evaluate_ask_refusal_message_matches_reason"]
