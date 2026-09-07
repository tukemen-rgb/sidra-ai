"""Does ``sidra-ask`` give a refusal the exit code that matches its cause?

C-1456: the CLI documents exit 3 as a safety refusal and exit 1 as an API
error, and its own tests say the codes exist so "a caller can tell 'the gate
stopped this' from 'the API is down', which are opposite problems". But
``render`` returned 3 for *every* refusal, so a **model backend unavailable**
outage - an operational failure the docstring assigns to exit 1 - came back
under the code a script uses for a policy refusal. A monitor keying on exit 3
would file a backend outage as a content-policy event and never page anyone.

The exit code now follows the cause: a gate block/quarantine and an output
guard that withheld a generated answer are safety refusals (3); a model
backend that never produced an answer is operational (1).

The checks call the real ``render`` and the real ``main`` (``--json``) with a
stub transport, and read the exit code.
"""

from __future__ import annotations

import io
import contextlib
from dataclasses import dataclass

_GATE_BLOCK = {"refused": True, "answer": "", "security": {"decision": "block"}, "citations": []}
_GATE_QUAR = {"refused": True, "answer": "", "security": {"decision": "quarantine"}, "citations": []}
_HISTORY = {"refused": True, "answer": "", "reason": "conversation history blocked by security gate",
            "security": {"decision": "block"}, "citations": []}
_OUTPUT_GUARD = {"refused": True, "answer": "", "reason": "model output withheld by security guard",
                 "security": {"decision": "allow"}, "model": {"backend": "echo"}, "citations": []}
_MODEL_DOWN = {"refused": True, "answer": "", "reason": "model backend unavailable",
               "security": {"decision": "allow"}, "citations": []}
_ANSWERED = {"refused": False, "answer": "回答です。", "security": {"decision": "allow"},
             "model": {"backend": "echo"}, "citations": []}


@dataclass(frozen=True)
class CliRefusalExitResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _render_code(payload: dict) -> int:
    from sidra_ai.api.ask_cli import render

    with contextlib.redirect_stdout(io.StringIO()):
        return render(dict(payload))


def _json_code(payload: dict) -> int:
    """Drive ``main`` down the --json branch with a stub transport."""
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
    ask_cli.get_settings = lambda: Settings(data_dir="/tmp/sidra-eval-cli")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return ask_cli.main(["質問", "--json"], client=_Client())
    finally:
        ask_cli.get_settings = original


def evaluate_cli_refusal_exit_code_by_cause() -> CliRefusalExitResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # render(): safety refusals are 3, an operational one is 1, an answer is 0.
    add(_render_code(_GATE_BLOCK) == 3, "gate block was not exit 3")
    add(_render_code(_GATE_QUAR) == 3, "gate quarantine was not exit 3")
    add(_render_code(_HISTORY) == 3, "history-gate block was not exit 3")
    add(_render_code(_OUTPUT_GUARD) == 3, "output-guard withholding was not exit 3")
    add(_render_code(_MODEL_DOWN) == 1, "model-backend-unavailable was not exit 1")
    add(_render_code(_ANSWERED) == 0, "an answered response was not exit 0")

    # --json carries the same distinction, not a blanket 3.
    add(_json_code(_MODEL_DOWN) == 1, "--json model-unavailable was not exit 1")
    add(_json_code(_GATE_BLOCK) == 3, "--json gate block was not exit 3")
    add(_json_code(_ANSWERED) == 0, "--json answered was not exit 0")

    total = 9
    return CliRefusalExitResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["CliRefusalExitResult", "evaluate_cli_refusal_exit_code_by_cause"]
