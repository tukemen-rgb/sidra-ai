"""A default that names a model tag is wrong on every machine but one.

``scripts/setup_real_model.py`` is the first thing the owner runs on his own
PC. It used to default ``--model`` to ``qwen2.5:3b``, and that default has
already cost him a round trip: the tag on his machine is
``qwen2.5:3b-instruct-q4_K_M``, so a plain run failed with "that model is not
installed" while the model he wanted was sitting right there in the list the
error printed.

The quantization is chosen for the card, so the exact tag differs on every
machine - which makes a hard-coded default authoritative-looking and wrong
essentially always. There is no default now: with one model installed there is
nothing to guess, and with several the script lists them and stops rather than
choosing for somebody. That refusal is the same one this script already makes
about values it cannot measure ("量子化ラベルが取得できません（推測では書きません）");
picking a model on the operator's behalf would be the same guess wearing a
convenience.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import setup_real_model  # noqa: E402

#: The owner's real tag, and the one the old default guessed at. Written apart
#: so this file records the actual incident rather than a made-up example.
OWNERS_TAG = "qwen2.5:3b-instruct-q4_K_M"
THE_OLD_DEFAULT = "qwen2.5:3b"


def test_the_single_installed_model_is_used_without_being_named() -> None:
    tag, note = setup_real_model.choose_model("", [OWNERS_TAG])

    assert tag == OWNERS_TAG
    assert OWNERS_TAG in note, "the choice must be stated, not made silently"


def test_the_old_default_no_longer_decides_anything() -> None:
    """The exact failure the owner hit, asked of the current code."""

    tag, note = setup_real_model.choose_model("", [OWNERS_TAG])

    assert tag != THE_OLD_DEFAULT
    source = (ROOT / "scripts" / "setup_real_model.py").read_text(encoding="utf-8")
    default = re.search(r'"--model",\s*\n?\s*default=("[^"]*")', source)
    assert default, "could not find the --model default to check"
    assert default.group(1) == '""', (
        f"--model defaults to {default.group(1)}, which is a guess about a "
        "machine this code has never seen"
    )


def test_several_models_are_listed_rather_than_chosen_between() -> None:
    installed = [OWNERS_TAG, "llama3.1:8b-instruct-q4_0", "phi3:mini"]

    tag, note = setup_real_model.choose_model("", installed)

    assert tag == "", "the script picked one of three for the operator"
    for name in installed:
        assert name in note, f"{name} was not offered"
    assert "--model" in note, "the message must say how to decide"


def test_an_empty_ollama_says_so_plainly() -> None:
    tag, note = setup_real_model.choose_model("", [])

    assert tag == ""
    assert "ollama pull" in note.lower()


def test_an_explicitly_named_model_is_honoured() -> None:
    tag, note = setup_real_model.choose_model(OWNERS_TAG, [OWNERS_TAG, "phi3:mini"])

    assert tag == OWNERS_TAG
    assert note == "", "an explicit choice needs no commentary"


def test_a_named_model_that_is_absent_shows_what_is_there() -> None:
    """The recovery path the owner actually used: the list in the error."""

    tag, note = setup_real_model.choose_model(THE_OLD_DEFAULT, [OWNERS_TAG])

    assert tag == ""
    assert THE_OLD_DEFAULT in note
    assert OWNERS_TAG in note, "the message must show what is installed instead"


def test_the_runbook_still_names_a_tag_explicitly() -> None:
    """Removing the default must not make the runbook's command ambiguous.

    The runbook passes --model on purpose, so the owner's copy-paste keeps
    working and stays reproducible even on a machine with several models.
    """

    runbook = (ROOT / "docs" / "RUNBOOK_CODER_MODEL_SWAP.md").read_text(
        encoding="utf-8"
    )
    assert "setup_real_model.py --model " in runbook
