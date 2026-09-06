"""C-1278: the CLI connection error names the knob the reader used.

sidra-ask's ConnectError always said 「SIDRA_HOST / SIDRA_PORT を確認」, even when
the target came from --url. It now names --url when that flag was given and the
env vars otherwise, so the reader is pointed at the setting they actually used.
"""

from __future__ import annotations

import contextlib
import io

import httpx

from sidra_ai.api.ask_cli import main
from sidra_ai.evals.cli_connect_error_names_used_knob import (
    evaluate_cli_connect_error_names_used_knob,
)


class _ConnectErrorClient:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}

    def post(self, url, json=None):  # noqa: A002
        raise httpx.ConnectError("refused")


def _stderr(argv):
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        code = main(argv, client=_ConnectErrorClient())
    return code, buf.getvalue()


def test_cli_connect_error_names_used_knob_eval_passes():
    result = evaluate_cli_connect_error_names_used_knob()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5


def test_url_case_names_url_not_env():
    code, err = _stderr(["質問", "--url", "http://127.0.0.1:8123/"])
    assert code == 1
    assert "--url" in err
    assert "SIDRA_HOST" not in err


def test_default_case_names_env_not_url():
    code, err = _stderr(["質問"])
    assert code == 1
    assert "SIDRA_HOST" in err and "SIDRA_PORT" in err
    assert "--url" not in err
