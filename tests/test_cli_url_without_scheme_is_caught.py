"""C-1936: a schemeless --url is bad usage (exit 2), not a transport failure.

base_url passed a schemeless --url through, httpx raised UnsupportedProtocol,
and the generic HTTPError branch reported 「通信に失敗した…」 at exit 1 - an outage
code for a typo. It is now caught before the request, exit 2, naming the scheme
to add, like --top-k/--timeout/--repository (C-1661/1669/1673).
"""

from __future__ import annotations

import contextlib
import io

import pytest

from sidra_ai.api import ask_cli
from sidra_ai.config.settings import Settings
from sidra_ai.evals.cli_url_without_scheme_is_caught import (
    evaluate_cli_url_without_scheme_is_caught,
)


class _Resp:
    status_code = 200

    def json(self):
        return {"refused": False, "answer": "ok", "refusal": "",
                "security": {"decision": "allow"}, "model": {"backend": "echo"},
                "citations": []}


class _Stub:
    def __init__(self):
        self.headers = {}
        self.posted = False

    def post(self, *a, **k):
        self.posted = True
        return _Resp()

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(
        ask_cli, "get_settings",
        lambda: Settings(data_dir="/tmp/sidra-c1936-test", host="127.0.0.1", port=8787),
    )


def _run(argv, client):
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        code = ask_cli.main(argv, client=client)
    return code, err.getvalue()


def test_eval_passes():
    result = evaluate_cli_url_without_scheme_is_caught()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 20


def test_schemeless_url_exits_2_and_names_the_fix_without_reaching_the_client():
    stub = _Stub()
    code, err = _run(["q", "--url", "example.com:1234"], stub)
    assert code == 2
    assert "http:// か https://" in err
    assert "通信に失敗した" not in err
    assert stub.posted is False  # exits before any request (and before the token host check)


def test_well_formed_url_proceeds():
    code, err = _run(["q", "--url", "http://host:9999"], _Stub())
    assert code == 0
    assert "http:// か https://" not in err
