"""How long the weights stay loaded is the operator's call, and only theirs.

The first question of a session pays for loading the model when Ollama has
already unloaded it - five minutes after the last one, by Ollama's own
default. None of this project's numbers can see that cost: it happens on the
machine that holds the weights, and every harness here runs on the echo
backend. So the setting exists, and these tests pin the two things that would
make it dishonest:

* an unset value must send **nothing**, so the daemon keeps its own default
  rather than having this project's opinion applied under its name;
* a value that is not a duration must be refused at configuration time, not
  interpolated into a request body and discovered as a confusing backend
  error much later.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.config.settings import Settings, UnsafeConfigurationError  # noqa: E402
from sidra_ai.models.base import GenerationRequest  # noqa: E402
from sidra_ai.models.http_backends import OllamaAdapter  # noqa: E402


def _request() -> GenerationRequest:
    return GenerationRequest(
        system_prompt="s",
        user_message="q",
        data_context="",
        temperature=0.1,
        max_output_tokens=64,
    )


def test_an_unset_keep_alive_sends_nothing() -> None:
    adapter = OllamaAdapter(model="m", endpoint="http://127.0.0.1:11434")
    assert "keep_alive" not in adapter._payload(_request(), stream=False)


def test_a_set_keep_alive_reaches_the_request_verbatim() -> None:
    adapter = OllamaAdapter(
        model="m", endpoint="http://127.0.0.1:11434", keep_alive="30m"
    )
    payload = adapter._payload(_request(), stream=False)
    assert payload["keep_alive"] == "30m"


def test_it_applies_to_streaming_too() -> None:
    """A setting that only half the code paths honour is worse than none."""

    adapter = OllamaAdapter(
        model="m", endpoint="http://127.0.0.1:11434", keep_alive="-1"
    )
    assert adapter._payload(_request(), stream=True)["keep_alive"] == "-1"


@pytest.mark.parametrize("value", ["30m", "-1", "0", "2h", "1h30m", "45s", "600"])
def test_durations_ollama_documents_are_accepted(value: str) -> None:
    Settings(model_keep_alive=value).validate()


@pytest.mark.parametrize(
    "value",
    [
        "forever",
        "30 m",
        '"30m"',
        "30m\nmodel: other",
        "30m; rm -rf /",
        "{\"a\": 1}",
    ],
)
def test_anything_that_is_not_a_duration_is_refused_at_startup(value: str) -> None:
    with pytest.raises(UnsafeConfigurationError):
        Settings(model_keep_alive=value).validate()


def test_the_default_configuration_is_unchanged() -> None:
    assert Settings().model_keep_alive == ""
