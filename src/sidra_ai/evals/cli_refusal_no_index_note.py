"""After a safety refusal, does the CLI blame the index for the missing answer?

C-1254: ``sidra-ask`` refused a prompt-injection input (quarantine) and then
printed 「引用なし。索引に根拠が無いか、取り込みがまだ走っていない。」 - the
no-evidence note, which reads as "re-run ingestion", when the real reason was
the safety gate. The web UI shows nothing for empty citations and is fine; only
the CLI carried the misleading line into the refusal path. A refusal now omits
the index note, while a genuine no-evidence answer keeps it.

The checks render a refused payload and a no-evidence payload through the CLI's
own ``render`` and read what a terminal would show.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from dataclasses import dataclass

_INDEX_NOTE_FRAGMENTS = ("索引に根拠が無い", "取り込みがまだ走っていない")


@dataclass(frozen=True)
class CliRefusalNoIndexNoteResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _render(payload: dict) -> tuple[str, int]:
    from sidra_ai.api.ask_cli import render

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = render(payload)
    return buf.getvalue(), code


def evaluate_cli_refusal_no_index_note() -> CliRefusalNoIndexNoteResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    refused = {
        "refused": True,
        "answer": "",
        "reason": "prompt-injection patterns detected; content remains DATA",
        "security": {"decision": "quarantine"},
        "citations": [],
    }
    out, code = _render(refused)

    # 1: the refusal itself is shown.
    add("拒否" in out, "refusal message not shown")
    # 2,3: the misleading index/ingestion note is gone from a refusal.
    for frag in _INDEX_NOTE_FRAGMENTS:
        add(frag not in out, f"refusal still prints the index note: 「{frag}」")
    # 4: the refusal exit code is unchanged.
    add(code == 3, f"refusal exit code changed (got {code})")

    # 5: a genuine no-evidence answer STILL explains the empty index - the note
    # is only wrong after a refusal, not in general.
    no_evidence = {
        "refused": False,
        "answer": "現時点では十分な根拠がありません。",
        "citations": [],
        "model": {},
    }
    out2, code2 = _render(no_evidence)
    add(
        any(frag in out2 for frag in _INDEX_NOTE_FRAGMENTS) and code2 == 0,
        "no-evidence answer lost its index note",
    )

    return CliRefusalNoIndexNoteResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=5,
        failures=tuple(failures),
    )


__all__ = ["CliRefusalNoIndexNoteResult", "evaluate_cli_refusal_no_index_note"]
