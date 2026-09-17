"""Does every conversational refusal get exit code 4, not 1 (outage)?

C-1931, the coverage-completing sibling of C-1811. ``_refusal_exit_code`` gives
a conversational refusal - a greeting, help, an ask-back, a "which one?" - exit
4, distinct from a safety block (3) and a backend outage (1), so a monitor
keying on exit 1 does not read the system-working-as-intended as an outage. But
the set ``_CONVERSATIONAL_REFUSALS`` listed only some codes: ``how_to_make``
(C-1875) was added to the service without being added here, so
「レポートの作り方を教えて」 fell through to exit 1 - a "how do I make one" answer
reported as an API outage. The existing exit-code eval tested only four codes
and missed it.

This eval asserts every conversational refusal code the service emits gets exit
4 through both the human ``render`` path and the ``--json`` path, and keeps the
safety (3) / outage (1) / answered (0) controls so the fix cannot widen too far.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass

#: Every refusal code that means "the system understood non-corpus input and
#: responded" - none is an error or a safety block. Each must exit 4.
CONVERSATIONAL_CODES: tuple[str, ...] = (
    "greeting", "help", "empty", "ambiguous", "unnamed", "revision_target",
    "delete_unsupported", "artifact_list", "artifact_feature_question",
    "panel_setting", "revision_change", "revision_kind", "how_to_make",
)

#: decision=allow, no model block: the shape a backend outage also has, which is
#: why a missing code falls to exit 1.
def _payload(code: str) -> dict:
    return {
        "refused": True,
        "answer": "…",  # non-empty so artifact_list's listing branch has a body
        "refusal": code,
        "security": {"decision": "allow"},
        "citations": [],
    }


_SAFETY_GATE = {"refused": True, "answer": "", "refusal": "gate",
                "security": {"decision": "block"}, "citations": []}
_OUTPUT_GUARD = {"refused": True, "answer": "", "refusal": "output_guard",
                 "security": {"decision": "allow"}, "model": {"backend": "echo"},
                 "citations": []}
_OUTAGE = {"refused": True, "answer": "", "refusal": "model_unavailable",
           "security": {"decision": "allow"}, "citations": []}
_ANSWERED = {"refused": False, "answer": "回答です。", "refusal": "",
             "security": {"decision": "allow"}, "model": {"backend": "echo"},
             "citations": []}


@dataclass(frozen=True)
class CliConversationalExitResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _render_code(payload: dict) -> int:
    from sidra_ai.api.ask_cli import render
    with contextlib.redirect_stdout(io.StringIO()):
        return render(dict(payload))


def _json_code(payload: dict) -> int:
    from sidra_ai.api import ask_cli
    from sidra_ai.config.settings import Settings

    class _Resp:
        status_code = 200

        def json(self):
            return payload

    class _Client:
        def __init__(self):
            self.headers = {}

        def post(self, *a, **k):
            return _Resp()

        def close(self):
            pass

    original = ask_cli.get_settings
    ask_cli.get_settings = lambda: Settings(data_dir="/tmp/sidra-eval-c1931")
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return ask_cli.main(["a question", "--json"], client=_Client())
    finally:
        ask_cli.get_settings = original


def evaluate_cli_conversational_refusals_exit_4() -> CliConversationalExitResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # (A) every conversational code exits 4 through both paths.
    for code in CONVERSATIONAL_CODES:
        p = _payload(code)
        rc_r = _render_code(p)
        rc_j = _json_code(p)
        add(rc_r == 4, f"A render: {code} -> {rc_r} (want 4)")
        add(rc_j == 4, f"A --json: {code} -> {rc_j} (want 4)")

    # (B) the controls: safety=3, outage=1, answered=0 (fix must not widen).
    add(_render_code(_SAFETY_GATE) == 3, "B: gate block not 3")
    add(_render_code(_OUTPUT_GUARD) == 3, "B: output_guard not 3")
    add(_render_code(_OUTAGE) == 1, "B: model_unavailable not 1")
    add(_render_code(_ANSWERED) == 0, "B: answered not 0")

    total = len(CONVERSATIONAL_CODES) * 2 + 4
    return CliConversationalExitResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "CONVERSATIONAL_CODES",
    "CliConversationalExitResult",
    "evaluate_cli_conversational_refusals_exit_4",
]
