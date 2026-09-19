"""C-1981: a malformed conversation history is screened, not a crash.

SidraService.chat's history loop raised on a wrong-arity tuple, a bare string,
None, or (None, None), though its docstring promises "a client can put anything
at all in history". _coerce_history_turn normalizes each entry to a (str, str)
pair first; the security screen (poisoned history is refused) is unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sidra_ai.api.service import SidraService, _coerce_history_turn
from sidra_ai.config.settings import Settings
from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.evals.chat_history_survives_malformed_shapes import (
    evaluate_chat_history_survives_malformed_shapes,
)
from sidra_ai.ingestion.state import StateStore


def test_eval_passes():
    result = evaluate_chat_history_survives_malformed_shapes()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total


@pytest.mark.parametrize(
    "entry",
    [("only-one",), "just a string", "hi", None, ("a", "b", "c"), 42, {"a": 1}],
)
def test_malformed_entries_are_dropped(entry):
    assert _coerce_history_turn(entry) is None


def test_none_fields_become_empty_strings():
    assert _coerce_history_turn((None, None)) == ("", "")


def test_list_pair_is_coerced():
    assert _coerce_history_turn(["q", "a"]) == ("q", "a")


def test_normal_pair_unchanged():
    assert _coerce_history_turn(("question", "answer")) == ("question", "answer")


@pytest.fixture()
def service(tmp_path) -> SidraService:
    return SidraService(
        Settings(data_dir=str(tmp_path), model_backend="echo"),
        state_store=StateStore(tmp_path / "state.json"),
    )


@pytest.mark.parametrize(
    "hist",
    [[("only-one",)], ["a string"], [None], [(None, None)], [["q", "a"]]],
)
def test_chat_does_not_crash_on_malformed_history(service, hist):
    # Must not raise; a clean question still produces a well-formed response.
    result = service.chat("デプロイの承認は誰がする", history=hist)
    assert isinstance(result, dict)
    assert result.get("refusal") != "gate"
