"""The return-day instrument must say what went wrong, once, in Japanese.

This is the script the owner runs on the machine, alone, after three weeks
away. It has already failed him once in the way that matters: fifteen
questions, fifteen identical ``NG ... (URLError)`` lines, and nothing to
distinguish "the server is not running" from "the token is wrong" from "the
model is still loading". A class name is not a diagnosis, and one broken
machine printed once per question looks like fifteen separate failures.

Two behaviours are pinned here.

**A cause that cannot change between questions stops the run.** Asking the
remaining fourteen learns nothing and buries the message under noise.

**A reachable server with an unreachable model is not a language failure.**
When the backend is down the answer is empty, and the old code scored that
empty string on the Japanese-share axis - reporting 0% Japanese, which is the
signature of the exact incident this instrument was built to catch (a Japanese
question answered in English, 2026-08-27). It would have pointed at the model's
prose when nothing had generated any prose at all. That is worse than no
measurement, because it is a confident wrong one.
"""

from __future__ import annotations

import http.client
import json
import socket
import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import check_model_answers as harness  # noqa: E402


def _japanese(text: str) -> bool:
    return any(
        0x3040 <= ord(character) <= 0x30FF or 0x4E00 <= ord(character) <= 0x9FFF
        for character in text
    )


# ------------------------------------------------------------- the diagnosis


def test_a_stopped_server_is_named_as_such_and_stops_the_run() -> None:
    message, fatal = harness.diagnose(urllib.error.URLError(ConnectionRefusedError()))

    assert fatal, "a server that is not running will not start between questions"
    assert _japanese(message)
    # The next step, in the words the runbook uses.
    assert "sidra_ai.api.server" in message


def test_a_rejected_token_is_not_confused_with_a_stopped_server() -> None:
    message, fatal = harness.diagnose(
        urllib.error.HTTPError("http://127.0.0.1:8787", 401, "Unauthorized", {}, None)
    )

    assert fatal
    assert "SIDRA_API_TOKEN" in message
    assert "起動していない" not in message, "this is an auth failure, not a dead server"


def test_a_timeout_does_not_stop_the_run() -> None:
    """One slow question is not a broken machine."""

    message, fatal = harness.diagnose(urllib.error.URLError(socket.timeout()))

    assert not fatal
    assert _japanese(message)


def test_every_diagnosis_is_japanese_and_names_no_internals() -> None:
    cases = [
        urllib.error.URLError(ConnectionRefusedError()),
        urllib.error.URLError(socket.timeout()),
        urllib.error.URLError(OSError("network is down")),
        urllib.error.HTTPError("u", 401, "x", {}, None),
        urllib.error.HTTPError("u", 429, "x", {}, None),
        urllib.error.HTTPError("u", 503, "x", {}, None),
        urllib.error.HTTPError("u", 418, "x", {}, None),
        socket.timeout(),
        http.client.RemoteDisconnected("closed"),
        json.JSONDecodeError("no", "doc", 0),
        RuntimeError("something else"),
    ]
    for exc in cases:
        message, _ = harness.diagnose(exc)
        assert message and _japanese(message), f"{type(exc).__name__}: {message!r}"
        # The operator's own text and the server's internals stay out of it.
        assert "Traceback" not in message
        assert "network is down" not in message


# ------------------------------------------------------------------ the run


def test_a_stopped_server_is_reported_once_not_once_per_question(capsys) -> None:
    calls = {"n": 0}

    def ask(question: str) -> dict:
        calls["n"] += 1
        raise urllib.error.URLError(ConnectionRefusedError())

    code = harness.main(ask)
    printed = capsys.readouterr().out

    assert code == 1, "a run that measured nothing must not report success"
    assert calls["n"] == 1, (
        f"asked {calls['n']} questions of a server that is not there; one is enough"
    )
    assert "測定を中止しました" in printed
    assert "sidra_ai.api.server" in printed


def test_an_unreachable_model_is_not_reported_as_a_language_failure(capsys) -> None:
    """The whole point: an empty answer from a dead backend is not 0% Japanese."""

    calls = {"n": 0}

    def ask(question: str) -> dict:
        calls["n"] += 1
        # Exactly what the service returns when the backend cannot be reached.
        return {
            "answer": "",
            "refused": True,
            "refusal": "model_unavailable",
            "reason": "model backend unavailable",
            "citations": [],
            "security": {"decision": "allow"},
        }

    code = harness.main(ask)
    printed = capsys.readouterr().out

    assert code == 1
    assert calls["n"] == 1, "the backend is down for every question, not just the first"
    assert "ローカルモデルに繋がっていません" in printed
    assert "echo" in printed, "the message must name the thing to check"
    # And it must not have scored the empty answer as prose.
    assert "日本語率" not in printed, (
        "an empty answer from a dead backend was scored on the language axis"
    )


def test_a_slow_question_does_not_abandon_the_rest(capsys) -> None:
    """A non-fatal failure keeps going, so one hiccup does not lose the run."""

    calls = {"n": 0}

    def ask(question: str) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError(socket.timeout())
        return {
            "answer": "収益化の方針は、掲載順を売らないことです。[S1]",
            "refused": False,
            "refusal": "",
            "citations": [{"label": "S1"}],
            "model": {"backend": "ollama"},
        }

    code = harness.main(ask)
    printed = capsys.readouterr().out

    assert code == 0
    assert calls["n"] == len(harness.QUESTIONS), "the run gave up on a single timeout"
    assert "測定を中止しました" not in printed
    assert f"設問 {len(harness.QUESTIONS) - 1}/{len(harness.QUESTIONS)} 問に回答" in printed


def test_a_healthy_run_is_unchanged(capsys) -> None:
    """The reporting this replaces must still work when nothing is wrong."""

    def ask(question: str) -> dict:
        return {
            "answer": "収益化の方針は、掲載順を売らないことです。[S1]",
            "refused": False,
            "refusal": "",
            "citations": [{"label": "S1"}],
            "model": {"backend": "ollama"},
        }

    code = harness.main(ask)
    printed = capsys.readouterr().out

    assert code == 0
    assert "測定を中止しました" not in printed
    assert f"設問 {len(harness.QUESTIONS)}/{len(harness.QUESTIONS)} 問に回答" in printed
    assert "日本語率" in printed
