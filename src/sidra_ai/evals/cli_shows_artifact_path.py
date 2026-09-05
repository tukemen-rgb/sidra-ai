"""When you make something from the CLI, does it tell you where the file is?

C-1262: ``sidra-ask 「レースゲームを作って」`` printed 「『レース』を作りました…」 and
then 「引用なし。索引に根拠が無いか、取り込みがまだ走っていない。」 - no path to the
file it just wrote, and a misleading index note on a creation response that has
no index citations by nature. The web UI has an artifact list; the CLI user was
left with a summary and nowhere to look. ``render`` now prints the artifact path
for a creation response and suppresses the empty-index note there, the same way
C-1254 suppressed it after a refusal - while a genuine Q&A answer keeps it.

The checks render real creation payloads (through the service) and a synthetic
no-evidence payload through the CLI's own ``render`` and read what a terminal
would show.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

_INDEX_NOTE = "取り込みがまだ走っていない"
_FILE_LABEL = "生成ファイル"


@dataclass(frozen=True)
class CliShowsArtifactPathResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _render(payload: dict) -> str:
    from sidra_ai.api.ask_cli import render

    buf = io.StringIO()
    with redirect_stdout(buf):
        render(payload)
    return buf.getvalue()


def _service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    return SidraService(Settings(data_dir=str(Path(tempfile.mkdtemp(prefix="cli-artifact-")) / "s")))


def evaluate_cli_shows_artifact_path() -> CliShowsArtifactPathResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    service = _service()

    # A real creation that writes a file.
    made = service.chat("レースゲームを作って")
    path = ((made.get("creation") or {}).get("outcome") or {}).get("artifact_path") or ""
    out = _render(made)
    # 1: the path to the written file is shown.
    add(bool(path) and path in out, f"artifact path not shown: 「{out.strip()[:80]}」")
    # 2: no misleading empty-index note on a creation response.
    add(_INDEX_NOTE not in out, "creation output still prints the index note")

    # A genuine no-evidence Q&A keeps the index note (C-1254's correct case).
    # Routed through the service on purpose: a real reply always carries a
    # `creation.intent` block even for a question, and a probe that omitted it
    # would miss a fix that keyed on `creation` being present at all.
    out_qa = _render(service.chat("天気を教えて"))
    # 3: the note still explains an empty index for a real question.
    add(_INDEX_NOTE in out_qa, "no-evidence Q&A lost its index note")

    # A creation we cannot build (C-1261): no file, so no file line, and still
    # no index note (it is a creation response, not a question).
    declined = service.chat("Excelを作って")
    out_decl = _render(declined)
    # 4: no bogus file line when nothing was written.
    add(_FILE_LABEL not in out_decl, "a declined creation printed a file line")
    # 5: and no misleading index note on the decline.
    add(_INDEX_NOTE not in out_decl, "a declined creation still prints the index note")

    return CliShowsArtifactPathResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=5,
        failures=tuple(failures),
    )


__all__ = ["CliShowsArtifactPathResult", "evaluate_cli_shows_artifact_path"]
