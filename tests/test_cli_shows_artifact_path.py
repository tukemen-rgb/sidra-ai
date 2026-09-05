"""C-1262: the CLI names the file a creation wrote and drops the index note.

`sidra-ask 「レースゲームを作って」` printed the summary but not the path to the
file, plus the misleading empty-index note on a creation response. render() now
shows the artifact path and suppresses that note for creations, keyed on the
creation *outcome* (every reply carries creation.intent, so keying on the path,
not the key, is what keeps a plain question's index note intact).
"""

from __future__ import annotations

import io
import tempfile
from contextlib import redirect_stdout

from sidra_ai.api import ask_cli
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.cli_shows_artifact_path import evaluate_cli_shows_artifact_path

_NOTE = "取り込みがまだ走っていない"


def _service() -> SidraService:
    return SidraService(Settings(data_dir=tempfile.mkdtemp(prefix="cli-artifact-test-")))


def _render(payload: dict) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        ask_cli.render(payload)
    return buf.getvalue()


def test_cli_shows_artifact_path_eval_passes():
    result = evaluate_cli_shows_artifact_path()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5


def test_creation_shows_path_and_no_index_note():
    payload = _service().chat("レースゲームを作って")
    path = payload["creation"]["outcome"]["artifact_path"]
    out = _render(payload)
    assert path in out
    assert "生成ファイル" in out
    assert _NOTE not in out


def test_question_keeps_index_note():
    # A real reply carries a creation.intent block even for a question, so the
    # note must survive that - keyed on the outcome, not the creation key.
    out = _render(_service().chat("天気を教えて"))
    assert _NOTE in out
    assert "生成ファイル" not in out


def test_declined_creation_has_no_path_line_and_no_note():
    out = _render(_service().chat("Excelを作って"))
    assert "生成ファイル" not in out
    assert _NOTE not in out
