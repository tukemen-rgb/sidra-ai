"""Does ``sidra-ask`` tell the user what to do for an unnamed creation request?

C-1769. A creation ask that names nothing ("なにか作って") is refused with
``refusal="unnamed"`` and a genuinely helpful answer listing what can be built.
The web UI has dedicated wording for ``unnamed`` (ui.py), but the CLI's ``render``
refusal-message map had no ``unnamed`` entry, so it fell to the generic "wait and
retry" fallback - advice the code's own tests document as wrong here (retrying the
same two words gets the same result). Its siblings ``empty`` and ``ambiguous`` are
in the map; ``unnamed`` was the odd one out. ``render`` now names the two next
steps directly, the way ``ambiguous`` does (the CLI does not print the answer body
on a refusal, so it cannot point at the menu the web UI shows).

The checks drive the real ``ask_cli.render`` with synthetic and real payloads.
"""

from __future__ import annotations

from sidra_ai.evals.scratch import scratch_dir

import contextlib
import io
from dataclasses import dataclass

# The generic fallback that must NOT be shown for a known ask-back code.
_FALLBACK = "少し時間をおいて、もう一度試す"

# Every refusal code SidraService can set (mirrors the web page's contract set).
_SERVICE_CODES = (
    "gate", "history", "model_unavailable", "output_guard",
    "empty", "ambiguous", "unnamed",
)


def _render_output(refusal: str, decision: str = "allow") -> str:
    from sidra_ai.api import ask_cli

    payload = {
        "refused": True,
        "refusal": refusal,
        "security": {"decision": decision},
        "answer": "",
        "citations": [],
    }
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        ask_cli.render(payload)
    return out.getvalue()


@dataclass(frozen=True)
class UnnamedResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_says_what_to_do_for_unnamed() -> UnnamedResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    unnamed_out = _render_output("unnamed")
    ambiguous_out = _render_output("ambiguous")

    # --- (A) unnamed does not get the "wait and retry" fallback ----------
    add(_FALLBACK not in unnamed_out,
        f"A: unnamed still shows the wait-and-retry fallback: {unnamed_out!r}")

    # --- (B) unnamed names a concrete next step -------------------------
    add("名指して" in unnamed_out or "作りたいもの" in unnamed_out,
        f"B: unnamed does not name a next step: {unnamed_out!r}")

    # --- (C) every service refusal code gets a non-fallback message -----
    missing = [c for c in _SERVICE_CODES if _FALLBACK in _render_output(c)]
    add(not missing, f"C: these refusal codes fall back to wait-and-retry: {missing}")

    # --- (D) an unknown code still uses the generic fallback (preserved) -
    add(_FALLBACK in _render_output("bogus_code_xyz"),
        "D: the generic fallback for an unknown code was lost")

    # --- (E) unnamed wording is its own, not the fallback or ambiguous ---
    add(_FALLBACK not in unnamed_out and unnamed_out != ambiguous_out,
        "E: unnamed wording is not distinct from the fallback/ambiguous")

    # --- (F) the real service refusal renders without the fallback ------
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    svc = SidraService(Settings(data_dir=scratch_dir()))
    real = svc.chat("なにか作って")  # "make me something"
    real_out = io.StringIO()
    with contextlib.redirect_stdout(real_out):
        from sidra_ai.api import ask_cli
        ask_cli.render(real)
    add(real.get("refusal") == "unnamed" and _FALLBACK not in real_out.getvalue(),
        f"F: real unnamed refusal misrendered: refusal={real.get('refusal')!r} "
        f"out={real_out.getvalue()!r}")

    total = 6
    return UnnamedResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["UnnamedResult", "evaluate_cli_says_what_to_do_for_unnamed"]
