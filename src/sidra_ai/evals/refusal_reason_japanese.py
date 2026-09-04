"""Does a refused question read in Japanese to the user, not English audit text?

C-1238: when the safety gate refused a message, the service put the gate's own
English audit reasons ("prompt-injection patterns detected; content remains
DATA and is held out of the index until reviewed") into the response's reason
field, and both the web page and the CLI showed that string verbatim -
「拒否されました: <English>」. A Japanese user got dense English jargon and no
idea what to change, against SYSTEM_PROMPT rule 6.

The API reason stays English for API consumers and the audit trail; the two
user-facing surfaces now show a Japanese message chosen by the machine-readable
security.decision: a gate refusal (quarantine/block) asks the user to rephrase,
any other refusal asks them to retry later. The raw English reason is not shown.

CLI checks drive render(); web checks read the served ASK_PAGE.
"""

from __future__ import annotations

import io
import re
from contextlib import redirect_stdout
from dataclasses import dataclass

_ENGLISH = "prompt-injection patterns detected; content remains DATA and is held out of the index until reviewed"
_REPHRASE = "言い換え"  # gate refusal guidance
_RETRY = "もう一度"     # other refusal guidance


@dataclass(frozen=True)
class RefusalReasonJapaneseResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _cli(payload: dict) -> str:
    from sidra_ai.api.ask_cli import render

    out = io.StringIO()
    with redirect_stdout(out):
        render(payload)
    return out.getvalue()


def evaluate_refusal_reason_japanese() -> RefusalReasonJapaneseResult:
    checks = 0
    failures: list[str] = []

    gate_refusal = {
        "answer": "",
        "refused": True,
        "reason": _ENGLISH,
        "security": {"decision": "quarantine"},
        "citations": [],
    }
    other_refusal = {
        "answer": "",
        "refused": True,
        "reason": "model backend unavailable",
        "security": {"decision": "allow"},
        "citations": [],
    }

    # --- CLI ---
    gate_out = _cli(gate_refusal)
    if _REPHRASE in gate_out:
        checks += 1
    else:
        failures.append("CLI: gate refusal gives no Japanese rephrase guidance")
    if _ENGLISH not in gate_out:
        checks += 1
    else:
        failures.append("CLI: the raw English audit reason is shown to the user")

    other_out = _cli(other_refusal)
    if _RETRY in other_out:
        checks += 1
    else:
        failures.append("CLI: a non-gate refusal gives no Japanese retry guidance")
    if "model backend unavailable" not in other_out:
        checks += 1
    else:
        failures.append("CLI: the raw English reason is shown for a non-gate refusal")

    # A normal answer is still printed (the refusal path did not swallow it).
    normal = _cli({"answer": "答えです。", "refused": False, "citations": []})
    if "答えです。" in normal:
        checks += 1
    else:
        failures.append("CLI: a normal answer stopped printing")

    # --- web UI (page source) ---
    from sidra_ai.api.ui import ASK_PAGE

    # The refusal branch reads security.decision to choose the message.
    if re.search(r"security[^\n]{0,40}decision", ASK_PAGE) or re.search(r"\.decision", ASK_PAGE):
        checks += 1
    else:
        failures.append("web: refusal does not branch on security.decision")
    if _REPHRASE in ASK_PAGE:
        checks += 1
    else:
        failures.append("web: no Japanese rephrase guidance on the page")
    if _RETRY in ASK_PAGE:
        checks += 1
    else:
        failures.append("web: no Japanese retry guidance on the page")
    # The refusal branch no longer concatenates the raw result.reason.
    if not re.search(r'\"\s*:\s*\"\s*\+\s*result\.reason', ASK_PAGE) and "result.reason" not in ASK_PAGE:
        checks += 1
    else:
        failures.append("web: the raw result.reason is still shown on refusal")

    return RefusalReasonJapaneseResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=9,
        failures=tuple(failures),
    )
