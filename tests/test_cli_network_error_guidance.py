"""C-1233: the CLI's transport catch-all gives guidance, not a class name.

A mid-answer disconnect (RemoteProtocolError) or a bad --url scheme
(UnsupportedProtocol) used to print 「要求に失敗した: <English class>」 with no
next step. It now gives actionable Japanese guidance, keeps the class in
parentheses for debugging, and exits non-zero, while the ConnectError and
timeout branches keep their own specific advice.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr

import httpx

from sidra_ai.api.ask_cli import main
from sidra_ai.evals.cli_network_error_guidance import (
    evaluate_cli_network_error_guidance,
)


def _run(exc: Exception) -> tuple[int, str]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x")
    err = io.StringIO()
    with redirect_stderr(err):
        code = main(["質問"], client=client)
    return code, err.getvalue()


def test_cli_network_error_guidance_eval_passes():
    result = evaluate_cli_network_error_guidance()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


def test_mid_answer_disconnect_gives_guidance_not_class_name():
    req = httpx.Request("POST", "http://x/v1/chat")
    rc, err = _run(httpx.RemoteProtocolError("peer closed", request=req))
    assert rc == 1
    assert "確認する" in err
    # The class name is kept only as a parenthetical debug token.
    assert "RemoteProtocolError" in err
    assert not err.strip().startswith("要求に失敗した:")


def test_connect_and_timeout_keep_their_own_advice():
    req = httpx.Request("POST", "http://x/v1/chat")
    rc, err = _run(httpx.ConnectError("refused", request=req))
    assert rc == 1 and "接続できない" in err
    rc, err = _run(httpx.ConnectTimeout("slow", request=req))
    assert rc == 1 and "応答が無かった" in err
