"""C-1275: sidra-ask names every file a multi-file creation wrote.

The CLI printed only artifact_path, so a 3D model's .obj/.mtl and a deck's .pptx
had no path in the terminal though the summary told the reader to open them
(C-1262, for the other files). The render now names every written *_path detail;
a single-file creation is unchanged.
"""

from __future__ import annotations

import contextlib
import io

from sidra_ai.api.ask_cli import render
from sidra_ai.evals.cli_names_all_generated_files import (
    evaluate_cli_names_all_generated_files,
)


def _render(payload: dict) -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        render(payload)
    return buffer.getvalue()


def _creation(artifact_path: str, details: dict) -> dict:
    return {
        "answer": "作りました。",
        "citations": [],
        "creation": {"outcome": {"artifact_path": artifact_path, "details": details}},
    }


def test_cli_names_all_generated_files_eval_passes():
    result = evaluate_cli_names_all_generated_files()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5


def test_3d_model_names_obj_and_mtl():
    out = _render(_creation(
        "a/m-preview.html", {"obj_path": "a/m.obj", "mtl_path": "a/m.mtl"}
    ))
    assert "a/m-preview.html" in out
    assert "a/m.obj" in out
    assert "a/m.mtl" in out


def test_single_file_creation_unchanged():
    out = _render(_creation("a/art.html", {"pattern": "flowfield", "seed": 3}))
    assert "a/art.html" in out
    # a non-path detail is never printed as a file
    assert "flowfield" not in out


def test_empty_secondary_path_is_not_printed():
    out = _render(_creation("a/deck.html", {"pptx_path": ""}))
    assert ".pptx" not in out
