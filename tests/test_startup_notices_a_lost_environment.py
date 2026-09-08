"""The one startup failure that succeeds: echo on a machine set up for a model.

On Windows the environment belongs to the terminal window. Setting
``SIDRA_MODEL_BACKEND`` in one window and starting the server from another
loses it, the process falls back to ``echo``, and then *everything works* -
the server starts, answers questions, and reports itself healthy, using a
backend that produces no model output at all. There is no error to read.

The owner lost time to precisely this on 2026-09-02. The banner said
``model backend : echo`` and nothing marked that as unintended, so the
subsequent answers were read as the model's.

The evidence that distinguishes "meant it" from "lost it" is on disk: the
reviewed manifest is written by ``scripts/setup_real_model.py`` and only
exists because somebody staged a real model *on this machine*. Echo plus a
staged manifest is the shape of the accident. Echo alone is the clean-machine
default and must stay silent, or the warning becomes noise and stops being
read - which is the failure mode of every warning that fires too often.

It warns and does not refuse. Running echo on a machine that also has a real
model staged is legitimate - it is how the offline suite is run - so this says
what it sees and gets out of the way.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sidra_ai.api.model_admission import MODEL_MANIFEST_FILENAME  # noqa: E402
from sidra_ai.api.server import (  # noqa: E402
    _print_banner,
    staged_model_but_running_echo,
)
from sidra_ai.config.settings import Settings  # noqa: E402


def _stage_a_manifest(directory: Path) -> None:
    (directory / MODEL_MANIFEST_FILENAME).write_text("{}", encoding="utf-8")


def test_echo_on_a_machine_with_a_staged_model_is_called_out(tmp_path) -> None:
    _stage_a_manifest(tmp_path)

    warning = staged_model_but_running_echo(
        Settings(data_dir=str(tmp_path), model_backend="echo")
    )

    assert warning, "the accident's exact shape produced no warning"
    # It has to name the variable and the reason, not merely observe echo.
    assert "SIDRA_MODEL_BACKEND" in warning
    assert "ウィンドウ" in warning


def test_a_clean_machine_says_nothing(tmp_path) -> None:
    """Echo with no staged model is the documented default, not a mistake."""

    warning = staged_model_but_running_echo(
        Settings(data_dir=str(tmp_path), model_backend="echo")
    )

    assert warning == "", (
        "a warning on every echo start is a warning nobody reads by the third day"
    )


def test_a_real_backend_says_nothing(tmp_path) -> None:
    _stage_a_manifest(tmp_path)

    for backend in ("ollama", "llama_cpp"):
        warning = staged_model_but_running_echo(
            Settings(data_dir=str(tmp_path), model_backend=backend)
        )
        assert warning == "", f"{backend} was warned about"


def test_an_unreadable_data_directory_is_not_an_excuse_to_crash(tmp_path) -> None:
    """Startup must not fall over because a warning could not be computed."""

    missing = tmp_path / "does-not-exist" / "nested"

    warning = staged_model_but_running_echo(
        Settings(data_dir=str(missing), model_backend="echo")
    )

    assert warning == ""


def test_the_banner_actually_prints_it(capsys, tmp_path) -> None:
    """The function being right is not the same as the operator seeing it."""

    _stage_a_manifest(tmp_path)
    settings = Settings(data_dir=str(tmp_path), model_backend="echo")

    _print_banner(settings)
    printed = capsys.readouterr().out

    assert "model backend : echo" in printed
    assert "SIDRA_MODEL_BACKEND" in printed, (
        "the warning was computed but never reached the terminal"
    )


def test_the_banner_stays_quiet_when_there_is_nothing_to_say(
    capsys, tmp_path
) -> None:
    settings = Settings(data_dir=str(tmp_path), model_backend="echo")

    _print_banner(settings)
    printed = capsys.readouterr().out

    assert "model backend : echo" in printed
    assert "注意" not in printed


def test_the_warning_leaks_no_paths_or_model_names(tmp_path) -> None:
    """The banner is terminal output, but the disclosure rules do not pause."""

    _stage_a_manifest(tmp_path)
    settings = Settings(
        data_dir=str(tmp_path), model_backend="echo", model_name="secret-model-tag"
    )

    warning = staged_model_but_running_echo(settings)

    assert warning, "the fixture must produce a warning for this to mean anything"
    assert str(tmp_path) not in warning
    assert "secret-model-tag" not in warning
