"""Does `sidra-quarantine show --content` scrub terminal-hostile characters?

C-1647. Quarantine review shows the operator the very content the gate flagged
as dangerous, so they can decide whether to release it. ``show --content``
printed that content raw - the gate redacts secrets but leaves control bytes -
so a quarantined document carrying ANSI/OSC escapes, bidi overrides or
zero-width characters could move the reviewer's cursor, retitle or clear their
terminal, or hide text at the exact moment they are judging it. C-1627 gave
the ask CLI this defense; the review CLI, the more dangerous surface, lacked it.

The checks build a quarantine log with one hostile entry and one clean entry,
run the real ``quarantine_cli.main``, and assert the content stream carries no
control bytes while the benign text and tabs survive, the operator is told how
many characters were removed, and the clean entry (and the no-``--content``
path) print no such warning.
"""

from __future__ import annotations

import io
import json
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

_ESC = chr(0x1B)
_BEL = chr(0x07)
_CSI = chr(0x9B)     # a C1 control
_ZWSP = chr(0x200B)  # zero width space
_RLO = chr(0x202E)   # right-to-left override
_TAB = chr(0x09)


def _write_log(directory: str) -> Path:
    path = Path(directory) / "quarantine.jsonl"
    hostile = (
        f"before{_TAB}mid {_ESC}[31mFAKE-ALLOW{_ESC}[0m {_ESC}]0;pwned{_BEL} "
        f"{_CSI}2J {_RLO}reversed{_ZWSP} after end"
    )
    clean = "an ordinary quarantined sentence with no control characters here"
    records = [
        {
            "recorded_at": "2026-09-10T21:15:00Z",
            "gate": {"decision": "quarantine", "reasons": ["prompt_injection detected"],
                     "findings": [{"severity": "high", "category": "prompt_injection",
                                   "detector": "override_instructions", "reason": "ignore previous"}]},
            "provenance": {"repository": "tukemen-rgb/site", "source": "github", "source_type": "docs"},
            "content_retention": "sanitized",
            "original_length": len(hostile),
            "document_id": "hostile01",
            "content": hostile,
        },
        {
            "recorded_at": "2026-09-10T21:16:00Z",
            "gate": {"decision": "quarantine", "reasons": ["secret detected"],
                     "findings": [{"severity": "high", "category": "secret",
                                   "detector": "github_token", "reason": "token-like"}]},
            "provenance": {"repository": "tukemen-rgb/site", "source": "github", "source_type": "docs"},
            "content_retention": "sanitized",
            "original_length": len(clean),
            "document_id": "clean01",
            "content": clean,
        },
    ]
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    return path


def _run(path: Path, argv):
    from sidra_ai.security import quarantine_cli

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = quarantine_cli.main(["--path", str(path), *argv])
    return code, out.getvalue(), err.getvalue()


def _entry_ids(path: Path):
    from sidra_ai.security.quarantine_review import QuarantineReview

    review = QuarantineReview(path)
    return {e.document_id: e.id for e in review.entries()}


@dataclass(frozen=True)
class QuarantineScrubResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_quarantine_show_scrubs_terminal_controls() -> QuarantineScrubResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    directory = tempfile.mkdtemp()
    path = _write_log(directory)
    ids = _entry_ids(path)
    hostile_id, clean_id = ids["hostile01"], ids["clean01"]

    # --- hostile entry, with content ---
    code, out, err = _run(path, ["show", hostile_id, "--content"])
    add(code == 0, f"hostile show exit {code}")
    for name, ch in (("ESC", _ESC), ("BEL", _BEL), ("C1/CSI", _CSI), ("ZWSP", _ZWSP), ("RLO", _RLO)):
        add(ch not in out, f"hostile content stream still carries raw {name}")
    add("FAKE-ALLOW" in out and "before" in out and "after end" in out,
        "hostile content lost its benign text")
    add(_TAB in out, "tab (harmless) was stripped from content")
    add("端末制御" in err or "control" in err.lower(),
        f"no removal notice on stderr: {err!r}")
    # the notice should carry a positive count
    add(any(str(n) in err for n in range(1, 40)) and ("端末制御" in err or "control" in err.lower()),
        f"removal notice omits a count: {err!r}")

    # --- hostile entry, WITHOUT --content: no content section, no notice ---
    code2, out2, err2 = _run(path, ["show", hostile_id])
    add(code2 == 0 and "redacted content" not in out2,
        "no-content show printed a content section")
    add("端末制御" not in err2 and "control" not in err2.lower(),
        f"no-content show emitted a strip notice: {err2!r}")

    # --- clean entry with content: shown, no strip notice ---
    code3, out3, err3 = _run(path, ["show", clean_id, "--content"])
    add(code3 == 0 and "no control characters here" in out3,
        "clean content not shown")
    add("端末制御" not in err3 and "control" not in err3.lower(),
        f"clean entry emitted a spurious strip notice: {err3!r}")

    total = 14
    return QuarantineScrubResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "QuarantineScrubResult",
    "evaluate_quarantine_show_scrubs_terminal_controls",
]
