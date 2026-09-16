"""C-1879: sidra-ask shows the made list, not a broken command, for 「作ったものを見せて」.

The refusal path printed 「回答を拒否した」 with no list and named
`sidra-ask --artifacts`, a flag the parser does not define. These tests pin that
the CLI now shows the service's answer body, drops the false command, and that no
refusal advice names a non-existent sidra-ask flag.
"""

from __future__ import annotations

import contextlib
import io
import re
import tempfile
from pathlib import Path

from sidra_ai.api import ask_cli
from sidra_ai.api.ask_cli import render
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.cli_artifact_list_shows_the_list import (
    evaluate_cli_artifact_list_shows_the_list,
)
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.gate import GatePolicy, SecurityGate


def _render(data_dir):
    gate = SecurityGate(GatePolicy(), allowed_repositories=("acme/app",))
    svc = SidraService(Settings(data_dir=str(data_dir)),
                       model=EchoModelAdapter(), store=DocumentStore(gate), gate=gate)
    payload = svc.chat("作ったものを見せて")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = render(dict(payload))
    return buf.getvalue(), code


def test_eval_passes():
    result = evaluate_cli_artifact_list_shows_the_list()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


def test_empty_list_shows_body_not_broken_command(tmp_path):
    out, code = _render(tmp_path)
    assert "まだ何も作っていません" in out
    assert "回答を拒否した" not in out
    assert "--artifacts" not in out
    assert code == 4


def test_populated_list_shows_the_file_name(tmp_path):
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "game-night.html").write_text("<html>g</html>")
    out, _ = _render(tmp_path)
    assert "game-night.html" in out
    assert "--artifacts" not in out


def test_no_refusal_advice_names_a_nonexistent_flag():
    valid = set()
    for action in ask_cli.build_parser()._actions:
        valid.update(action.option_strings)
    src = Path(ask_cli.__file__).read_text(encoding="utf-8")
    referenced = set(re.findall(r"sidra-ask (--[A-Za-z0-9][A-Za-z0-9-]*)", src))
    assert not (referenced - valid)
