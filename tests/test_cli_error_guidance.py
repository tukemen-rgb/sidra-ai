"""C-1223: sidra-ask must say what to do when a request fails.

The web page maps each reachable HTTP status class to Japanese guidance, but
the CLI only special-cased 401 and 429 - a too-long question printed a bare
「API がエラーを返した: HTTP 422」. The CLI now maps 403, 413/422 and 5xx too,
with the code printed for debugging and the response body left unread.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr

import httpx

from sidra_ai.api.ask_cli import main
from sidra_ai.evals.cli_error_guidance import evaluate_cli_error_guidance


def _run(status: int) -> tuple[int, str]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "SECRET-BODY"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x")
    err = io.StringIO()
    with redirect_stderr(err):
        code = main(["質問"], client=client)
    return code, err.getvalue()


def test_cli_error_guidance_eval_passes():
    result = evaluate_cli_error_guidance()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 16


def test_too_long_message_gets_guidance_not_bare_code():
    rc, err = _run(422)
    assert rc == 1
    assert "短く" in err and "再送" in err
    assert "422" in err
    assert "SECRET-BODY" not in err


def test_forbidden_and_server_error_have_guidance():
    _, forbidden = _run(403)
    assert "トークン" in forbidden and "403" in forbidden
    _, server = _run(503)
    assert "サーバ" in server and "503" in server
