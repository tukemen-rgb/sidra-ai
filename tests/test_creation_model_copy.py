"""The model's one hole into an artifact, and every way it stays shut.

`GeneratedGame.with_copy` shipped with the generator and was never called by
anything (C-1027). These tests pin the wiring in both directions: a backend
that answers reaches the saved page, and every failure - prose, a franchise
name, an oversized value, markup, an exception, the echo default - leaves the
deterministic page byte-identical to the one built with no model at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sidra_ai.creation.copy_writer import (
    ArtifactCopy,
    build_copy_writer,
    copy_metadata,
    parse_copy,
)
from sidra_ai.creation.game_job import build_game_generator
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.models.base import GenerationResult, LocalModelAdapter
from sidra_ai.models.echo import EchoModelAdapter

_ASK = "釣りゲームを作って"


class FakeLocalModel(LocalModelAdapter):
    """Not echo, so the writer will actually consult it."""

    backend = "fake-local"

    def __init__(self, text: str = "", *, fail: bool = False) -> None:
        super().__init__("fake-local-1")
        self.text = text
        self.fail = fail
        self.requests: list[object] = []

    def generate(self, request):  # noqa: ANN001 - test double
        self.requests.append(request)
        if self.fail:
            raise RuntimeError("backend down")
        return GenerationResult(text=self.text, backend=self.backend, model=self.model)


def _run(tmp_path: Path, model: LocalModelAdapter | None):
    writer = build_copy_writer(model) if model is not None else None
    return build_game_generator(tmp_path, writer)(_ASK, detect_creation_intent(_ASK))


def test_a_model_that_answers_names_the_page_that_gets_saved(tmp_path):
    model = FakeLocalModel('{"title": "朝凪の一本", "tagline": "潮が動く前に。"}')
    outcome = _run(tmp_path, model)

    assert outcome.details["model_copy"] is True
    assert outcome.details["model_title"] == "朝凪の一本"
    assert outcome.details["playable"] is True
    page = Path(outcome.artifact_path).read_text(encoding="utf-8")
    assert "朝凪の一本" in page
    assert "潮が動く前に。" in page


def test_the_request_goes_up_but_no_retrieved_data_does(tmp_path):
    # A playable page must not carry indexed content; the model that names
    # one is therefore offered none.
    model = FakeLocalModel('{"title": "朝凪の一本"}')
    _run(tmp_path, model)

    assert len(model.requests) == 1
    sent = model.requests[0]
    assert sent.data_context == ""
    assert _ASK in sent.user_message


@pytest.mark.parametrize(
    "model",
    [
        pytest.param(FakeLocalModel("Sure! How about Fishing Time?"), id="prose"),
        pytest.param(FakeLocalModel("{"), id="broken-json"),
        pytest.param(FakeLocalModel('["朝凪"]'), id="not-an-object"),
        pytest.param(FakeLocalModel('{"title": 7}'), id="not-a-string"),
        pytest.param(FakeLocalModel('{"title": "   "}'), id="blank"),
        pytest.param(FakeLocalModel('{"title": "' + "あ" * 400 + '"}'), id="oversized"),
        pytest.param(FakeLocalModel('{"title": "<b>釣り</b>"}'), id="markup"),
        pytest.param(FakeLocalModel('{"title": "ゼルダ風の釣り"}'), id="franchise"),
        pytest.param(FakeLocalModel("", fail=True), id="backend-down"),
        pytest.param(EchoModelAdapter(), id="echo-default"),
    ],
)
def test_every_failure_leaves_the_page_exactly_as_it_was(tmp_path, model):
    plain = _run(tmp_path, None)
    got = _run(tmp_path, model)

    assert got.details["model_copy"] is False
    assert got.details["model_title"] == ""
    assert got.summary == plain.summary
    assert got.details["playable"] is True


def test_the_echo_default_is_refused_before_the_call_not_after(tmp_path):
    # Asking echo and discarding its answer would spend a generation on
    # every request on every clean checkout.
    echo = EchoModelAdapter()
    calls = []
    original = echo.generate
    echo.generate = lambda request: calls.append(request) or original(request)  # type: ignore[method-assign]

    _run(tmp_path, echo)

    assert calls == []


def test_a_renamed_franchise_keeps_its_notice_even_when_the_model_speaks(tmp_path):
    # The title guard prints *why* it renamed the page. A model-written
    # tagline must not quietly delete that explanation.
    ask = "ドラゴンボールのゲームを作って"
    model = FakeLocalModel('{"title": "閃光の決闘", "tagline": "夜明けの空に。"}')
    outcome = build_game_generator(tmp_path, build_copy_writer(model))(
        ask, detect_creation_intent(ask)
    )

    page = Path(outcome.artifact_path).read_text(encoding="utf-8")
    assert "閃光の決闘" in page
    assert "オリジナル版" in page
    assert "ドラゴンボール" not in page


def test_a_paid_backend_never_becomes_a_copy_provider(tmp_path):
    # The registry refuses these at construction. This is a new call site,
    # so it refuses them too rather than inheriting the guarantee.
    model = FakeLocalModel('{"title": "朝凪の一本"}')
    model.requires_paid_api = True

    assert build_copy_writer(model)(_ASK) is None
    assert model.requests == []


def test_a_rejected_tagline_does_not_sink_an_accepted_title():
    copy = parse_copy('{"title": "朝凪の一本", "tagline": "<b>' + "あ" * 400 + '</b>"}')

    assert copy == ArtifactCopy("朝凪の一本", "")


def test_every_name_the_title_guard_rejects_is_rejected_here_too():
    # Two guards, one rule: a franchise the page-title guard renames must
    # not be reachable through the model instead. Checked by asking, so the
    # test survives either list being edited.
    from sidra_ai.creation.games import _TRADEMARKS

    for mark in _TRADEMARKS:
        assert parse_copy('{"title": "%sの冒険"}' % mark) is None, mark
    # ...plus the spellings a model reaches for and a request rarely does.
    assert parse_copy('{"title": "Zelda Fishing"}') is None
    assert parse_copy('{"title": "TETRIS 2"}') is None


def test_the_metadata_is_present_on_every_artifact_not_only_the_touched_ones():
    assert copy_metadata(None) == {
        "model_copy": False,
        "model_title": "",
        "model_tagline": "",
    }
    assert copy_metadata(ArtifactCopy("題", "一言"))["model_copy"] is True
