"""The model may choose the numbers - inside the shipped envelope (C-1135).

GPT-6 writes anything and nothing checks it; SIDRA checks everything and
writes the same page twice. 「レース作って」 twice gave two identical files,
because every number came from a table.

The answer here is not a random seed - that makes variety nobody chose. The
model proposes, and everything it proposes that the author did not ship is
thrown away: the proposal is folded into the same ``panel`` overrides a
sentence already produces (C-1117), so ``panel_schema`` clamps every axis to
the template's own easy..hard span, and the page is validated by the
existing checker before it is saved.

With no weights the backend is ``echo``, the proposer declines, and the page
is byte for byte the one today's table builds. That is what makes this
measurable in a container with no GPU.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from sidra_ai.creation.games import _DIFFICULTY, choose_template, validate_game_html
from sidra_ai.creation.game_job import build_game_generator
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.creation.proposer import build_param_proposer, parse_proposal
from sidra_ai.creation.tuning import panel_schema
from sidra_ai.models.base import GenerationResult

REQUEST = "レース作って"
TEMPLATE = choose_template(REQUEST)
BANDS = tuple(pair[1] for pair in _DIFFICULTY[TEMPLATE].values())


class FakeModel:
    """A model that answers with whatever reply the test wants to try."""

    requires_paid_api = False

    def __init__(self, text: str, backend: str = "llama") -> None:
        self.text = text
        self.backend = backend
        self.asked: list[str] = []

    def generate(self, request):
        self.asked.append(request.user_message)
        return GenerationResult(text=self.text, backend=self.backend, model="fake")


def build(proposer) -> str:
    """One generated page, read back off disk."""

    with tempfile.TemporaryDirectory() as data_dir:
        build_game_generator(data_dir, None, proposer)(
            REQUEST, detect_creation_intent(REQUEST)
        )
        pages = sorted(pathlib.Path(data_dir).rglob("*.html"))
        assert pages, "no page was written"
        return pages[0].read_text(encoding="utf-8")


# --- the parsing, without a model --------------------------------------


def test_only_the_known_keys_survive():
    kept = parse_proposal(
        '{"band": 200, "accent": "#4fd1c5", "daily": true, "eval": "rm -rf"}',
        bands=BANDS,
    )
    assert set(kept) == {"band", "accent", "daily"}


def test_a_band_outside_the_shipped_span_is_pulled_back_inside():
    low, high = min(BANDS), max(BANDS)
    assert parse_proposal('{"band": 9000}', bands=BANDS)["band"] == high
    assert parse_proposal('{"band": -1}', bands=BANDS)["band"] == low


def test_an_accent_that_is_not_a_colour_never_reaches_the_page():
    """The one field where a wrong shape is not merely a bad parameter.

    The accent is substituted into the artifact as an identifier, so a
    string that is not a colour is the one thing a model could put there
    that is not a parameter at all.
    """

    for bad in ('"red"', '"#12"', '"#4fd1c5; background:url(x)"', '"javascript:1"', "12"):
        assert "accent" not in parse_proposal('{"accent": %s}' % bad, bands=BANDS)
    assert parse_proposal('{"accent": "#4FD1C5"}', bands=BANDS)["accent"] == "#4fd1c5"


def test_a_reply_that_is_not_json_is_simply_no_proposal():
    for text in ("", "すみません、わかりません", "{", "[1,2,3]", "null"):
        assert parse_proposal(text, bands=BANDS) == {}


def test_an_explanation_around_the_object_is_still_a_proposal():
    """Small models like to explain themselves first."""

    kept = parse_proposal('はい、こうします:\n{"band": 200}\n以上です。', bands=BANDS)
    assert kept == {"band": 200.0}


def test_a_boolean_is_not_a_band():
    assert "band" not in parse_proposal('{"band": true}', bands=BANDS)


# --- the page, built for real ------------------------------------------


def test_echo_builds_exactly_the_page_the_table_always_built():
    """The default on a checkout with no weights: nothing changes."""

    silent = build_param_proposer(FakeModel('{"band": 9000}', backend="echo"))
    assert build(silent) == build(None)


def test_a_model_that_proposes_changes_the_page():
    proposing = build_param_proposer(FakeModel('{"band": 200, "accent": "#4fd1c5"}'))
    assert build(proposing) != build(None)


def test_two_proposals_are_two_different_pages():
    """The variety half: the same request, twice, is no longer one file."""

    first = build(build_param_proposer(FakeModel('{"accent": "#4fd1c5"}')))
    second = build(build_param_proposer(FakeModel('{"accent": "#ff8800"}')))
    assert first != second
    assert "#4fd1c5" in first and "#ff8800" in second


def test_an_absurd_proposal_still_builds_a_page_the_checker_passes():
    """The guarantee half, read off the existing instrument.

    A model asking for a band of 9000 gets the hardest value the author
    shipped - the page is still one the author could have shipped.
    """

    page = build(build_param_proposer(FakeModel('{"band": 9000, "accent": "#000000"}')))
    assert validate_game_html(page)["playable"], "an absurd proposal broke the page"
    fields = {
        f["key"]: f
        for f in panel_schema(
            TEMPLATE,
            _DIFFICULTY[TEMPLATE],
            difficulty="normal",
            accent="#000000",
            overrides=parse_proposal('{"band": 9000}', bands=BANDS),
        )["fields"]
    }
    assert min(BANDS) <= fields["band"]["default"] <= max(BANDS)


def test_a_model_that_raises_leaves_the_page_alone():
    """A broken model is a working page - the copy writer's rule too."""

    class Broken(FakeModel):
        def generate(self, request):
            raise RuntimeError("no weights")

    assert build(build_param_proposer(Broken("{}"))) == build(None)


def test_the_model_is_asked_about_numbers_and_shown_no_retrieved_content():
    """Nothing indexed reaches this call, so DATA has nothing to steer."""

    model = FakeModel('{"band": 200}')
    with tempfile.TemporaryDirectory() as data_dir:
        build_game_generator(data_dir, None, build_param_proposer(model))(
            REQUEST, detect_creation_intent(REQUEST)
        )
    assert model.asked and REQUEST in model.asked[0]
    assert "band range" in model.asked[0]
