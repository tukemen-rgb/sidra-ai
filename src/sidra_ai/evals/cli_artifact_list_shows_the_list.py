"""Does ``sidra-ask`` show the list it made - not a broken command - for 「作ったものを見せて」?

C-1879, the CLI-flag sibling of C-1873 (printed advice must actually work).
Asking the CLI to list what was made produced, via the real ``render``:

    回答を拒否した。
    作ったものの一覧を返した。ファイル本体は `sidra-ask --artifacts` か /v1/artifacts から取得する。

Three things wrong at once: it says 「回答を拒否した」 though nothing was refused
(a listing is an answer); it says 「一覧を返した」 while showing no list, because the
refusal path drops the answer body the service composed (「まだ何も作っていません…」
or 「これまでに作ったのは全 N 件…」); and it names ``sidra-ask --artifacts``, a
command this CLI has no flag for - running it exits 2 with "unrecognized arguments".

The fix shows the service's own answer body for ``artifact_list`` (it already
carries the list and the working ``/v1/artifacts`` reference) and skips the
「回答を拒否した」 line, and drops the canned pointer with its dead flag.

Driven through the real ``SidraService`` and the real ``ask_cli.render``, empty and
populated. A structural guard also checks that no refusal advice names a
``sidra-ask`` flag the parser does not define - the general form of the defect.
"""

from __future__ import annotations

import contextlib
import io
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CliArtifactListResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _render_list_query(*, make_artifact: bool) -> tuple[str, int, str]:
    """Return (rendered_output, exit_code, service_answer_body)."""
    from sidra_ai.api.ask_cli import render
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.evals.scratch import scratch_dir
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, SecurityGate

    data_dir = Path(scratch_dir("c1879-"))
    if make_artifact:
        art = data_dir / "artifacts"
        art.mkdir(parents=True, exist_ok=True)
        (art / "game-night.html").write_text("<html>game</html>", encoding="utf-8")

    gate = SecurityGate(GatePolicy(), allowed_repositories=("acme/app",))
    service = SidraService(
        Settings(data_dir=str(data_dir)),
        model=EchoModelAdapter(), store=DocumentStore(gate), gate=gate,
    )
    payload = service.chat("作ったものを見せて")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = render(dict(payload))
    return buf.getvalue(), code, str(payload.get("answer") or "")


def evaluate_cli_artifact_list_shows_the_list() -> CliArtifactListResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) empty index: the CLI shows the service's own answer body --------
    out, code, body = _render_list_query(make_artifact=False)
    add(body and body in out,
        f"A: empty-index output does not show the service list body: {out!r}")
    add("回答を拒否した" not in out,
        "A: a listing still prints 「回答を拒否した」 (it is not a refusal)")
    add("--artifacts" not in out,
        "A: the output still names the non-existent `sidra-ask --artifacts`")
    add(code == 4, f"A: artifact_list exit code is {code}, not 4 (conversational)")

    # --- (B) populated index: the made file's name reaches the reader --------
    out2, _code2, body2 = _render_list_query(make_artifact=True)
    add("game-night.html" in out2,
        f"B: the made artifact name is not shown: {out2!r}")
    add("回答を拒否した" not in out2, "B: populated listing prints 「回答を拒否した」")
    add("--artifacts" not in out2,
        "B: populated output still names `sidra-ask --artifacts`")

    # --- (C) no refusal advice names a sidra-ask flag the parser lacks -------
    from sidra_ai.api import ask_cli

    valid: set[str] = set()
    for action in ask_cli.build_parser()._actions:
        valid.update(action.option_strings)
    src = Path(ask_cli.__file__).read_text(encoding="utf-8")
    referenced = set(re.findall(r"sidra-ask (--[A-Za-z0-9][A-Za-z0-9-]*)", src))
    bad = sorted(r for r in referenced if r not in valid)
    add(not bad, f"C: refusal advice names non-existent sidra-ask flags: {bad}")

    return CliArtifactListResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = ["CliArtifactListResult", "evaluate_cli_artifact_list_shows_the_list"]
