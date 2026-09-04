"""C-1243: the CLI reports a config-safety error in Japanese, not English.

A config-safety failure printed 「refusing to ask: <English>」; the prefix is now
Japanese with a next step, and the exception detail (which names the setting to
fix) stays in parentheses. Other CLI paths are unaffected.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr

from sidra_ai.api import ask_cli
from sidra_ai.config import UnsafeConfigurationError
from sidra_ai.evals.cli_config_error_japanese import (
    evaluate_cli_config_error_japanese,
)


def test_cli_config_error_japanese_eval_passes():
    result = evaluate_cli_config_error_japanese()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5


def test_config_error_is_japanese_with_detail(monkeypatch):
    detail = "refusing to bind non-loopback host 'x': set SIDRA_ALLOW_PUBLIC_BIND=true"

    def _raise():
        raise UnsafeConfigurationError(detail)

    monkeypatch.setattr(ask_cli, "get_settings", _raise)
    err = io.StringIO()
    with redirect_stderr(err):
        code = ask_cli.main(["質問"])
    out = err.getvalue()
    assert code == 2
    assert "refusing to ask" not in out
    assert "設定" in out and ("見直" in out or "確認" in out)
    assert "SIDRA_ALLOW_PUBLIC_BIND" in out  # detail preserved
