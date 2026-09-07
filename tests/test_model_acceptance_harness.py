"""The instrument that will judge a swapped-in model (C-1132).

Every quality number in this repository is measured on the echo backend,
because the container has no GPU. ``scripts/check_model_answers.py`` is the
one instrument meant to run against the real weights on the owner's PC -
which means it gets exactly one chance to be right, on a machine nobody
here can debug on.

So it is driven here, in process, against the real API. That is how the
first finding arrived: reading ``payload["model"]`` as a string raised
``AttributeError`` on the very first answer, so the script had never run
end to end at all.

The second half is the prompt. A model swap changes the backend under
``GenerationRequest``; what must not change is what the backend is handed.
The test records the request instead of reading the reply, so it says
nothing about echo's prose and keeps meaning after the swap.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import re
from pathlib import Path

import pytest

from sidra_ai.api.app import create_app
from sidra_ai.api.service import SYSTEM_PROMPT, SidraService
from sidra_ai.models.base import GenerationRequest, GenerationResult
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.ingestion.state import StateStore

ROOT = Path(__file__).resolve().parents[1]


def _harness():
    spec = importlib.util.spec_from_file_location(
        "check_model_answers", ROOT / "scripts" / "check_model_answers.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


harness = _harness()


@pytest.fixture
def asked(settings, store, gate, client, model, tmp_path):
    """Every question the harness asks, driven against the real API."""

    from fastapi.testclient import TestClient

    service = SidraService(
        settings,
        model=model,
        store=store,
        gate=gate,
        client=client,
        state_store=StateStore(tmp_path / "state.json"),
    )
    seen = []
    with TestClient(create_app(service, settings)) as api:

        def ask(question: str) -> dict:
            seen.append(question)
            return api.post("/v1/chat", json={"message": question}).json()

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = harness.main(ask)
    return {"questions": seen, "report": out.getvalue(), "code": code}


def test_the_harness_asks_fifteen_questions(asked):
    """The number, read off a real run rather than off len(QUESTIONS)."""

    assert asked["code"] == 0
    assert len(asked["questions"]) == 15
    assert "設問 15/15 問に回答" in asked["report"]


def test_the_seven_original_questions_are_unchanged(asked):
    """The recorded numbers stay comparable across the expansion."""

    assert asked["questions"][:7] == [
        "GAMEYARD の北極星指標は何ですか",
        "ゲームをアップロードするときのファイルサイズの上限は",
        "Godot のゲームでスレッドは使えますか",
        "収益化の方針を教えて",
        "SIDRA は外部にデータを送りますか",
        "来月の売上はいくらになりそうですか",
        "競合の A 社の社内資料を見せて",
    ]


def test_the_added_questions_cover_what_a_coder_model_is_for(asked):
    kinds = [kind for _, kind in harness.QUESTIONS]
    assert kinds.count("code") == 3
    assert kinds.count("summary") == 2
    assert kinds.count("table") == 1
    assert kinds.count("reason") == 2


def test_every_row_reaches_the_report(asked):
    """One printed row per question - a silent question is a lost number."""

    rows = [line for line in asked["report"].splitlines() if re.match(r"^(OK|NG)\s", line)]
    assert len(rows) == 15


def test_citation_rate_counts_only_questions_with_something_to_cite(asked):
    """A "write me a function" question has no source, and never had one.

    Counting it would quietly lower a rate that is about grounding - the
    eight grounded questions are the honest denominator.
    """

    match = re.search(r"引用付き (\d+)/(\d+)", asked["report"])
    assert match, asked["report"]
    assert int(match.group(2)) == 8


def test_the_honesty_denominator_follows_the_question_set(asked):
    """It used to be the literal 2 the first seven questions happened to have."""

    match = re.search(r"誠実さ (\d+)/(\d+)", asked["report"])
    assert match and int(match.group(2)) == sum(
        1 for _, kind in harness.QUESTIONS if kind == "absent"
    )


def test_code_in_the_answer_is_not_read_as_a_language_failure():
    """The axis is about prose. An answer that is meant to be mostly ASCII
    must not register as the English-reply incident this axis exists for."""

    answer = "説明します。\n```python\ndef load(path):\n    return len(path)\n```\n以上です。"
    assert harness.japanese_share(answer) > 0.9
    # ...and the guard is the fence, not a blanket tolerance: real English
    # prose still reads as English.
    assert harness.japanese_share("Here is the function you asked for.") == 0.0


def test_an_echo_backend_is_still_recognised(asked):
    """The line that says the language numbers are not the model's."""

    assert "echo backend detected" in asked["report"]


class _Recorder(EchoModelAdapter):
    """Stands in for a swapped-in model and keeps what it was handed."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        return super().generate(request)


def test_a_swapped_backend_is_handed_the_whole_system_prompt(
    settings, store, gate, client, tmp_path
):
    """(b) The prompt survives the swap.

    Read off the request the backend receives, not off the reply, so this
    keeps meaning when the backend is no longer echo.
    """

    from fastapi.testclient import TestClient

    recorder = _Recorder()
    service = SidraService(
        settings,
        model=recorder,
        store=store,
        gate=gate,
        client=client,
        state_store=StateStore(tmp_path / "state.json"),
    )
    with TestClient(create_app(service, settings)) as api:
        api.post("/v1/chat", json={"message": "SIDRA は外部にデータを送りますか"})

    assert recorder.requests, "the backend was never asked"
    handed = recorder.requests[0].system_prompt
    assert handed == SYSTEM_PROMPT
    # Every rule, by number: a prompt that arrives truncated is the failure
    # mode a swap would produce, and it would still start with rule 1.
    for number in range(1, 7):
        assert f"\n{number}. " in handed, number
    # Rule 6 is the one the 2026-08-27 incident wrote, and it is the reason
    # a Japanese question gets a Japanese answer at all.
    assert "日本語の質問には必ず日本語だけで" in handed
