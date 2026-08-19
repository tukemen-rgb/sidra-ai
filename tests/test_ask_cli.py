"""``sidra-ask``: the shell path to an answer.

The CLI is thin on purpose - it adds no capability the API lacks - so most of
these tests are about the two things a thin client can still get wrong: where
it sends the bearer token, and what it hands to a terminal.
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from sidra_ai.api import ask_cli
from sidra_ai.api.app import create_app
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings, UnsafeConfigurationError
from sidra_ai.ingestion.state import StateStore
from sidra_ai.models.base import GenerationResult

TOKEN = "sidra-" + "t" * 30


@pytest.fixture
def service(settings: Settings, store, gate, client, model, tmp_path) -> SidraService:
    return SidraService(
        settings,
        model=model,
        store=store,
        gate=gate,
        client=client,
        state_store=StateStore(tmp_path / "state.json"),
    )


@pytest.fixture
def cli_client(service: SidraService, settings: Settings) -> TestClient:
    """A client wired straight to the app - real routing, no socket.

    ``TestClient`` is an ``httpx.Client``, so the CLI takes it unchanged and
    every request still goes through the real middleware, auth dependency and
    route handler.
    """
    return TestClient(create_app(service, settings))


@pytest.fixture(autouse=True)
def _configured_settings(monkeypatch: pytest.MonkeyPatch, settings: Settings):
    monkeypatch.setattr(ask_cli, "get_settings", lambda: settings)
    return settings


def _run(argv, client=None) -> int:
    return ask_cli.main(argv, client=client)


# --- the ordinary path -------------------------------------------------

def test_a_question_prints_the_answer_and_its_citations(
    cli_client, service: SidraService, capsys
) -> None:
    service.analyze_github(["tukemen-rgb/site"])

    code = _run(["What is the site repository?"], client=cli_client)
    out = capsys.readouterr().out

    assert code == 0
    assert "引用:" in out
    assert "tukemen-rgb/site" in out


def test_an_empty_index_says_so_instead_of_printing_nothing(cli_client, capsys) -> None:
    """A blank screen is indistinguishable from a broken tool."""
    code = _run(["anything at all"], client=cli_client)
    out = capsys.readouterr().out

    assert code == 0
    assert "引用なし" in out


def test_a_refusal_is_reported_and_exits_distinctly(cli_client, capsys) -> None:
    """A refusal is not an error, and not a success either.

    Its own exit code lets a caller tell "the gate stopped this" from "the
    API is down", which are opposite problems.
    """
    secret = "ghp_" + "5" * 36

    code = _run([f"is {secret} still valid?"], client=cli_client)
    captured = capsys.readouterr()

    assert code == 3
    assert "拒否" in captured.out
    assert secret not in captured.out + captured.err


def test_json_mode_emits_parseable_output(cli_client, service: SidraService, capsys) -> None:
    service.analyze_github(["tukemen-rgb/site"])

    code = _run(["What is the site repository?", "--json"], client=cli_client)
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["refused"] is False
    assert "citations" in payload


# --- where the token goes ----------------------------------------------

def test_the_token_reaches_the_configured_host(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setenv("SIDRA_API_TOKEN", TOKEN)

    headers = ask_cli.authorization_header(
        f"http://{settings.host}:{settings.port}", settings
    )

    assert headers == {"Authorization": f"Bearer {TOKEN}"}


def test_the_token_is_not_handed_to_a_host_that_was_not_configured(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """--url is a convenience; it is not permission to leak credentials."""
    monkeypatch.setenv("SIDRA_API_TOKEN", TOKEN)

    with pytest.raises(UnsafeConfigurationError):
        ask_cli.authorization_header("http://collector.invalid:9000", settings)


def test_a_foreign_url_refuses_before_any_request_and_prints_no_token(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setenv("SIDRA_API_TOKEN", TOKEN)

    def explode(*_args, **_kwargs):  # pragma: no cover - must never run
        raise AssertionError("a request was sent to an unconfigured host")

    monkeypatch.setattr(ask_cli, "ask", explode)

    code = _run(["question", "--url", "http://collector.invalid:9000"])
    captured = capsys.readouterr()

    assert code == 2
    assert TOKEN not in captured.out + captured.err


def test_no_token_configured_sends_no_authorization_header(settings: Settings) -> None:
    assert ask_cli.authorization_header("http://collector.invalid:9000", settings) == {}


# --- what reaches the terminal -----------------------------------------

def test_control_sequences_in_an_answer_are_stripped_and_reported(
    cli_client, service: SidraService, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Repository content is DATA, and a terminal executes some of it.

    The escape here clears the screen and the bidi override reverses the text
    that follows. Printed raw, a document could erase the citation naming it.
    """
    hostile = "\x1b[2Janswer‮txet desrever‬"
    original = service.model.generate

    def generate(request):
        result = original(request)
        return GenerationResult(
            text=hostile,
            backend=result.backend,
            model=result.model,
            input_tokens_estimate=result.input_tokens_estimate,
            output_tokens_estimate=result.output_tokens_estimate,
            finish_reason=result.finish_reason,
            metadata=result.metadata,
        )

    monkeypatch.setattr(service.model, "generate", generate)
    service.analyze_github(["tukemen-rgb/site"])

    code = _run(["What is the site repository?"], client=cli_client)
    captured = capsys.readouterr()

    assert code == 0
    assert "\x1b" not in captured.out
    assert "‮" not in captured.out
    assert "answer" in captured.out
    assert "端末制御文字" in captured.err


def test_json_mode_escapes_control_characters_rather_than_emitting_them(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """--json keeps the value intact without becoming an escape carrier.

    The formatted view strips; the raw view must not, or it would be useless
    for inspecting what actually came back. It stays safe because JSON
    encodes the escape as text rather than emitting it.
    """

    def hostile(*_args, **_kwargs):
        return httpx.Response(
            200, json={"answer": "\x1b[2Jgone", "refused": False, "citations": []}
        )

    monkeypatch.setattr(ask_cli, "ask", hostile)

    code = _run(["question", "--json"])
    out = capsys.readouterr().out

    assert code == 0
    assert "\x1b" not in out
    assert json.loads(out)["answer"] == "\x1b[2Jgone"


def test_stripping_leaves_ordinary_text_alone() -> None:
    clean = ask_cli._Stripped()

    assert clean("日本語 and English\n\ttabbed") == "日本語 and English\n\ttabbed"
    assert clean.removed == 0


# --- when the API is not there -----------------------------------------

def test_a_closed_port_says_the_api_is_not_running(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """The failure a first-time user hits, and the one worth a real message."""

    def refuse(*_args, **_kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(ask_cli, "ask", refuse)

    code = _run(["question"])
    err = capsys.readouterr().err

    assert code == 1
    assert "sidra-api" in err


def test_a_slow_backend_reports_the_timeout_and_how_to_raise_it(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def stall(*_args, **_kwargs):
        raise httpx.ReadTimeout("too slow")

    monkeypatch.setattr(ask_cli, "ask", stall)

    code = _run(["question", "--timeout", "1"])
    err = capsys.readouterr().err

    assert code == 1
    assert "--timeout" in err


def test_an_authentication_failure_points_at_the_token_not_the_question(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def unauthorized(*_args, **_kwargs):
        return httpx.Response(401, json={"detail": "invalid or missing bearer token"})

    monkeypatch.setattr(ask_cli, "ask", unauthorized)

    code = _run(["question"])
    err = capsys.readouterr().err

    assert code == 1
    assert "SIDRA_API_TOKEN" in err


def test_an_empty_question_is_rejected_before_a_request(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args, **_kwargs):  # pragma: no cover - must never run
        raise AssertionError("an empty question reached the API")

    monkeypatch.setattr(ask_cli, "ask", explode)

    assert _run(["   "]) == 2


# --- the entry point itself --------------------------------------------

def test_the_console_script_is_registered() -> None:
    """product_metrics.py reads this to decide whether asking is possible."""
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    scripts = pyproject["project"]["scripts"]

    assert scripts["sidra-ask"] == "sidra_ai.api.ask_cli:main"
